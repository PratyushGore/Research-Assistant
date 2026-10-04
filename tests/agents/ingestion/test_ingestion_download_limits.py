import os
import time
from unittest.mock import MagicMock, patch
import pytest

from backend.agents.ingestion.agent import (
    download_pdf,
    ingest_and_store_pdf,
)
from backend.schemas.schemas import PaperMetadata


@pytest.fixture(autouse=True)
def _isolated_pdf_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))


def test_cache_hit_makes_no_http_call(tmp_path, monkeypatch):
    """When a cached PDF is present, return it without making an HTTP request."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))

    url = "https://arxiv.org/abs/2301.00001"
    pdf_url = "https://arxiv.org/pdf/2301.00001"

    mock_response = MagicMock()
    mock_response.content = b"%PDF-1.4 test valid cached data"
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}
    mock_response.iter_content.return_value = [b"%PDF-1.4 test valid cached data"]

    with patch("backend.agents.ingestion.agent.requests.get", return_value=mock_response) as mock_get:
        # First download - should hit the network and write cache
        data1 = download_pdf(url)
        assert data1.startswith(b"%PDF")
        assert mock_get.call_count == 1

        mock_get.reset_mock()

        # Second download - should hit the disk cache with no network call
        data2 = download_pdf(url)
        assert data2 == data1
        mock_get.assert_not_called()


def test_size_cap_triggers_on_content_length(tmp_path, monkeypatch):
    """When Content-Length exceeds INGEST_MAX_PDF_MB, abort before downloading body."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("INGEST_MAX_PDF_MB", "2.0")

    url = "https://arxiv.org/abs/1905.09130v1"
    # 3.8 MB in bytes
    large_size = int(3.8 * 1024 * 1024)

    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": str(large_size)}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = MagicMock()

    with patch("backend.agents.ingestion.agent.requests.get", return_value=mock_response):
        with pytest.raises(ValueError) as exc_info:
            download_pdf(url)

        err_msg = str(exc_info.value)
        assert "PDF too large" in err_msg
        assert "3.8 MB > 2.0 MB" in err_msg
        assert "1905.09130v1" in err_msg
        # Body streaming must not have been initiated
        mock_response.iter_content.assert_not_called()


def test_size_cap_triggers_on_streamed_bytes(tmp_path, monkeypatch):
    """When Content-Length is missing, abort when streamed bytes exceed INGEST_MAX_PDF_MB."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("INGEST_MAX_PDF_MB", "1.0")  # 1 MB cap

    url = "https://example.com/unbounded.pdf"

    # Stream 3 chunks of 512 KB = 1.5 MB total (exceeds 1.0 MB cap)
    chunk = b"X" * (512 * 1024)
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content.return_value = [chunk, chunk, chunk]

    with patch("backend.agents.ingestion.agent.requests.get", return_value=mock_response):
        with pytest.raises(ValueError) as exc_info:
            download_pdf(url)

        err_msg = str(exc_info.value)
        assert "PDF too large" in err_msg
        assert "1.0 MB" in err_msg


def test_deadline_triggers(tmp_path, monkeypatch):
    """When elapsed time exceeds INGEST_DOWNLOAD_TIMEOUT_S, raise TimeoutError."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("INGEST_DOWNLOAD_TIMEOUT_S", "5")

    url = "https://arxiv.org/abs/slow_paper"

    mock_response = MagicMock()
    mock_response.headers = {}
    mock_response.raise_for_status = MagicMock()

    # Simulate chunks that cause elapsed time to exceed timeout
    chunk = b"Y" * 1024
    mock_response.iter_content.return_value = [chunk, chunk]

    # Advance time on each time.time() call
    fake_times = [100.0, 100.0, 110.0, 120.0]  # Jump by 10s > 5s
    with patch("backend.agents.ingestion.agent.requests.get", return_value=mock_response), \
         patch("backend.agents.ingestion.agent.time.time", side_effect=fake_times):
        with pytest.raises(TimeoutError) as exc_info:
            download_pdf(url)

        err_msg = str(exc_info.value)
        assert "timed out" in err_msg
        assert "slow_paper" in err_msg


def test_failed_download_is_not_cached(tmp_path, monkeypatch):
    """Never cache a failed download (validation failure, size error, or HTTP error)."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))

    # 1. Non-PDF bytes validation failure
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content.return_value = [b"<!DOCTYPE html><html><body>Error</body></html>"]

    with patch("backend.agents.ingestion.agent.requests.get", return_value=mock_response):
        with pytest.raises(ValueError):
            download_pdf("https://arxiv.org/abs/html_page")

    # Cache should be completely empty
    cached_files = os.listdir(tmp_path)
    assert len(cached_files) == 0, f"Found cached files after failed validation: {cached_files}"


@patch("backend.agents.ingestion.agent.add_chunks", return_value=1)
def test_ingest_and_store_pdf_distinguishes_reasons(mock_add_chunks, capsys, monkeypatch, tmp_path):
    """Verify ingest_and_store_pdf prints distinguishing reasons: too large, timed out, and other error."""
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))
    metadata = PaperMetadata(
        paper_id="arxiv:1905.09130v1",
        title="Test Paper",
        authors=["Author"],
        abstract="Abstract content for fallback.",
        year=2026,
    )

    # 1. Too large
    with patch("backend.agents.ingestion.agent.ingest_pdf", side_effect=ValueError("PDF too large: 3.8 MB > 2.0 MB for URL ...")):
        result = ingest_and_store_pdf("https://arxiv.org/abs/1905.09130v1", metadata=metadata)
        captured = capsys.readouterr()
        assert "Falling back to abstract for arxiv:1905.09130v1 (PDF too large: 3.8 MB > 2.0 MB)" in captured.out
        assert len(result.chunks) == 1

    # 2. Timed out
    with patch("backend.agents.ingestion.agent.ingest_pdf", side_effect=TimeoutError("Download timed out after 60s for URL ...")):
        result = ingest_and_store_pdf("https://arxiv.org/abs/1905.09130v1", metadata=metadata)
        captured = capsys.readouterr()
        assert "Falling back to abstract for arxiv:1905.09130v1 (timed out)" in captured.out
        assert len(result.chunks) == 1

    # 3. Other error
    with patch("backend.agents.ingestion.agent.ingest_pdf", side_effect=ValueError("Downloaded content from ... is not a valid PDF")):
        result = ingest_and_store_pdf("https://arxiv.org/abs/1905.09130v1", metadata=metadata)
        captured = capsys.readouterr()
        assert "Falling back to abstract for arxiv:1905.09130v1 (other error:" in captured.out
        assert len(result.chunks) == 1
