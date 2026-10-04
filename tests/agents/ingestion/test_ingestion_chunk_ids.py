from unittest.mock import MagicMock, patch
import fitz
import pytest

from backend.agents.ingestion.agent import (
    create_chunks,
    download_pdf,
    ingest_and_store_pdf,
    ingest_pdf_bytes,
)
from backend.schemas.schemas import PaperMetadata


def create_multi_page_pdf(num_pages: int = 3) -> bytes:
    """Create a multi-page test PDF in memory."""
    doc = fitz.open()
    for i in range(1, num_pages + 1):
        page = doc.new_page()
        # Insert enough text so each page generates multiple chunks with small chunk_size
        text = f"Page {i} content. " + ("Research finding detail sentence. " * 30)
        page.insert_text((50, 50), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_chunk_ids_unique_across_multiple_pages():
    """Chunk IDs should be unique and sequentially numbered across all pages."""
    pdf_bytes = create_multi_page_pdf(num_pages=3)
    metadata = PaperMetadata(
        paper_id="arxiv:123v1",
        title="Multi-page Paper",
        authors=["Author One"],
        year=2026,
    )

    result = ingest_pdf_bytes(
        pdf_bytes=pdf_bytes,
        metadata=metadata,
        chunk_size=300,
        chunk_overlap=50,
    )

    assert len(result.chunks) >= 3, "Expected multiple chunks across 3 pages"

    chunk_ids = [c.chunk_id for c in result.chunks]
    # Check that there are no duplicate chunk IDs
    assert len(chunk_ids) == len(set(chunk_ids)), f"Duplicate chunk IDs found: {chunk_ids}"

    # Verify sequential numbering across all pages: chunk:0, chunk:1, ...
    expected_ids = [f"arxiv:123v1:chunk:{i}" for i in range(len(result.chunks))]
    assert chunk_ids == expected_ids

    # Verify page numbers are preserved and span multiple pages
    page_numbers = {c.page_number for c in result.chunks}
    assert page_numbers == {1, 2, 3}


def test_create_chunks_direct_multi_page():
    """create_chunks directly produces unique chunk IDs across pages."""
    pages = [
        (1, "Page 1 start text. " + "Detailed discussion. " * 20),
        (2, "Page 2 continue text. " + "Detailed results. " * 20),
        (3, "Page 3 final text. " + "Detailed conclusion. " * 20),
    ]

    chunks = create_chunks(
        pages=pages,
        paper_id="paper-456",
        chunk_size=200,
        chunk_overlap=40,
    )

    chunk_ids = [c.chunk_id for c in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert chunk_ids == [f"paper-456:chunk:{i}" for i in range(len(chunks))]


@pytest.fixture(autouse=True)
def _isolated_pdf_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("RA_PDF_CACHE_DIR", str(tmp_path))


@patch("backend.agents.ingestion.agent.requests.get")
def test_abs_url_rewritten_to_pdf_url(mock_get):
    """An arXiv abs URL should be rewritten to https://arxiv.org/pdf/<id> before downloading."""
    mock_response = MagicMock()
    mock_response.content = b"%PDF-1.4 fake pdf data"
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    # Test standard https abs URL
    download_pdf("https://arxiv.org/abs/2301.00001")
    mock_get.assert_called_with(
        "https://arxiv.org/pdf/2301.00001",
        timeout=30,
        headers={"User-Agent": "Multi-Agent-Research-Assistant/1.0"},
        stream=True,
    )

    # Test http with version suffix
    download_pdf("http://arxiv.org/abs/2104.08653v2")
    mock_get.assert_called_with(
        "https://arxiv.org/pdf/2104.08653v2",
        timeout=30,
        headers={"User-Agent": "Multi-Agent-Research-Assistant/1.0"},
        stream=True,
    )

    # Test export.arxiv.org landing page
    download_pdf("https://export.arxiv.org/abs/cs/0101001")
    mock_get.assert_called_with(
        "https://arxiv.org/pdf/cs/0101001",
        timeout=30,
        headers={"User-Agent": "Multi-Agent-Research-Assistant/1.0"},
        stream=True,
    )


@patch("backend.agents.ingestion.agent.requests.get")
def test_non_pdf_bytes_raise_value_error(mock_get):
    """Downloaded content that does not begin with %PDF must raise a clear ValueError naming the URL."""
    mock_response = MagicMock()
    mock_response.content = b"<!DOCTYPE html><html><body>arXiv landing page boilerplate</body></html>"
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    target_url = "https://arxiv.org/abs/2301.00001"
    with pytest.raises(ValueError) as exc_info:
        download_pdf(target_url)

    error_msg = str(exc_info.value)
    assert "%PDF" in error_msg
    assert "https://arxiv.org/pdf/2301.00001" in error_msg


@patch("backend.agents.ingestion.agent.add_chunks")
@patch("backend.agents.ingestion.agent.ingest_pdf")
def test_abstract_fallback_returns_exactly_one_chunk(mock_ingest_pdf, mock_add_chunks):
    """When ingestion fails and metadata.abstract exists, return an IngestionResult with exactly one chunk."""
    metadata = PaperMetadata(
        paper_id="arxiv:2301.00001",
        title="Fallback Research Paper",
        authors=["Alice", "Bob"],
        abstract="This is the research paper abstract explaining the key discoveries.",
        year=2026,
        url="https://arxiv.org/abs/2301.00001",
    )

    mock_ingest_pdf.side_effect = ValueError(
        "Downloaded content from https://arxiv.org/pdf/2301.00001 is not a valid PDF"
    )
    mock_add_chunks.return_value = 1

    result = ingest_and_store_pdf(
        url="https://arxiv.org/abs/2301.00001",
        metadata=metadata,
    )

    assert len(result.chunks) == 1
    fallback_chunk = result.chunks[0]
    assert fallback_chunk.chunk_id == "arxiv:2301.00001:chunk:0"
    assert fallback_chunk.paper_id == "arxiv:2301.00001"
    assert fallback_chunk.text == metadata.abstract
    assert result.raw_text == metadata.abstract

    # Assert ChromaDB storage was invoked with the fallback chunk
    mock_add_chunks.assert_called_once_with([fallback_chunk])


@patch("backend.agents.ingestion.agent.add_chunks")
@patch("backend.agents.ingestion.agent.ingest_pdf")
def test_failure_without_abstract_returns_empty_result(mock_ingest_pdf, mock_add_chunks):
    """When ingestion fails and no abstract exists, return empty chunks."""
    metadata = PaperMetadata(
        paper_id="paper:no-abstract",
        title="Paper Without Abstract",
        authors=["Charlie"],
        abstract=None,
        year=2026,
    )

    mock_ingest_pdf.side_effect = Exception("Download failed")

    result = ingest_and_store_pdf(
        url="https://example.com/broken.pdf",
        metadata=metadata,
    )

    assert len(result.chunks) == 0
    assert result.raw_text is None
    mock_add_chunks.assert_not_called()
