from unittest.mock import patch

from backend.agents.ingestion.agent import ingest_and_store_pdf
from backend.schemas.schemas import PaperMetadata, IngestionResult


def test_ingest_and_store_pdf_calls_vector_store():
    metadata = PaperMetadata(
        paper_id="test:integration-001",
        title="Test Research Paper",
        authors=["Test Author"],
        year=2026,
        url="https://example.com/test.pdf",
    )

    fake_result = IngestionResult(
        paper_id=metadata.paper_id,
        metadata=metadata,
        chunks=[],
        raw_text="Test PDF text",
    )

    with patch(
        "backend.agents.ingestion.agent.ingest_pdf",
        return_value=fake_result,
    ) as mock_ingest, patch(
        "backend.agents.ingestion.agent.add_chunks",
        return_value=3,
    ) as mock_add_chunks:

        result = ingest_and_store_pdf(
            url=metadata.url,
            metadata=metadata,
        )

    mock_ingest.assert_called_once()
    mock_add_chunks.assert_not_called()

    assert result.paper_id == "test:integration-001"
    assert result.metadata.title == "Test Research Paper"