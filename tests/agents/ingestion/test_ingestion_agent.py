import fitz
import pytest

from backend.agents.ingestion.agent import (
    clean_text,
    create_chunks,
    extract_pdf_text,
    ingest_pdf_bytes,
)
from backend.schemas.schemas import PaperMetadata


def create_test_pdf():
    """Create a small PDF in memory for testing."""

    document = fitz.open()

    page1 = document.new_page()
    page1.insert_text(
        (50, 50),
        "This is page one of the test research paper. "
        "It contains sample research content."
    )

    page2 = document.new_page()
    page2.insert_text(
        (50, 50),
        "This is page two of the test research paper. "
        "It contains additional sample research content."
    )

    pdf_bytes = document.tobytes()

    document.close()

    return pdf_bytes


def test_pdf_text_extraction():
    """PDF text should be extracted correctly."""

    pdf_bytes = create_test_pdf()

    pages = extract_pdf_text(pdf_bytes)

    assert len(pages) == 2

    assert pages[0][0] == 1
    assert pages[1][0] == 2

    assert "page one" in pages[0][1]
    assert "page two" in pages[1][1]


def test_clean_text():
    """Extra spaces and empty lines should be cleaned."""

    text = """
    Hello       world.

    
    This is a test.
    """

    cleaned = clean_text(text)

    assert "Hello world." in cleaned
    assert "This is a test." in cleaned


def test_create_chunks():
    """Text should be divided into chunks."""

    pages = [
        (
            1,
            "A" * 2500,
        )
    ]

    chunks = create_chunks(
        pages=pages,
        paper_id="test-paper",
        chunk_size=1000,
        chunk_overlap=200,
    )

    assert len(chunks) > 1

    for chunk in chunks:
        assert chunk.paper_id == "test-paper"
        assert chunk.text
        assert chunk.page_number == 1


def test_invalid_chunk_parameters():

    pages = [
        (
            1,
            "Some research text."
        )
    ]

    with pytest.raises(ValueError):
        create_chunks(
            pages,
            "test-paper",
            chunk_size=0,
            chunk_overlap=0,
        )

    with pytest.raises(ValueError):
        create_chunks(
            pages,
            "test-paper",
            chunk_size=100,
            chunk_overlap=100,
        )


def test_ingestion_result():

    pdf_bytes = create_test_pdf()

    metadata = PaperMetadata(
        paper_id="test-paper",
        title="Test Research Paper",
        authors=["Test Author"],
        year=2026,
        url=None,
        venue="Test Venue",
    )

    result = ingest_pdf_bytes(
        pdf_bytes=pdf_bytes,
        metadata=metadata,
        chunk_size=500,
        chunk_overlap=100,
    )

    assert result.paper_id == "test-paper"

    assert result.metadata.title == (
        "Test Research Paper"
    )

    assert result.raw_text is not None

    assert len(result.chunks) > 0

    for chunk in result.chunks:
        assert chunk.paper_id == "test-paper"
        assert chunk.text
        assert chunk.page_number is not None


def test_invalid_pdf():

    invalid_pdf = b"This is not a real PDF."

    with pytest.raises(Exception):
        extract_pdf_text(invalid_pdf)