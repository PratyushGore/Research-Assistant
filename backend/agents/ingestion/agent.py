import io
import requests
import fitz

from backend.schemas.schemas import PaperMetadata, Chunk, IngestionResult
from backend.vectorstore.store import add_chunks


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DOWNLOAD_TIMEOUT = 30


def download_pdf(url: str) -> bytes:
    """Download a PDF from a URL."""
    response = requests.get(
        url,
        timeout=DOWNLOAD_TIMEOUT,
        headers={"User-Agent": "Multi-Agent-Research-Assistant/1.0"},
    )
    response.raise_for_status()
    return response.content


def extract_pdf_text(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text from each PDF page."""
    pages = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text")
            pages.append((page_number, text))

    return pages


def clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    return " ".join(text.split())


def create_chunks(
    pages: list[tuple[int, str]],
    paper_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Create overlapping text chunks from PDF pages."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks = []

    for page_number, page_text in pages:
        text = clean_text(page_text)

        if not text:
            continue

        start = 0
        chunk_number = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        chunk_id=f"{paper_id}:chunk:{chunk_number}",
                        paper_id=paper_id,
                        text=chunk_text,
                        section_heading=None,
                        page_number=page_number,
                    )
                )

            chunk_number += 1

            if end >= len(text):
                break

            start = end - chunk_overlap

    return chunks


def ingest_pdf_bytes(
    pdf_bytes: bytes,
    metadata: PaperMetadata,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionResult:
    """Extract and chunk a PDF already available as bytes."""

    pages = extract_pdf_text(pdf_bytes)

    chunks = create_chunks(
        pages=pages,
        paper_id=metadata.paper_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    raw_text = "\n".join(
        clean_text(text)
        for _, text in pages
        if clean_text(text)
    )

    return IngestionResult(
        paper_id=metadata.paper_id,
        metadata=metadata,
        chunks=chunks,
        raw_text=raw_text or None,
    )


def ingest_pdf(
    url: str,
    metadata: PaperMetadata,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionResult:
    """Download, extract, and chunk a PDF."""

    pdf_bytes = download_pdf(url)

    return ingest_pdf_bytes(
        pdf_bytes=pdf_bytes,
        metadata=metadata,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def ingest_local_pdf(
    file_path: str,
    metadata: PaperMetadata,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionResult:
    """Ingest a PDF stored locally."""

    with open(file_path, "rb") as file:
        pdf_bytes = file.read()

    return ingest_pdf_bytes(
        pdf_bytes=pdf_bytes,
        metadata=metadata,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def ingest_and_store_pdf(
    url: str,
    metadata: PaperMetadata,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestionResult:
    """
    Download, extract, chunk, and store PDF chunks in ChromaDB.

    If ingestion fails, log the error and return an empty result
    so that the overall research pipeline can continue.
    """

    try:
        result = ingest_pdf(
            url=url,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if result.chunks:
            stored_count = add_chunks(result.chunks)
            print(
                f"[Ingestion Agent] "
                f"{stored_count} chunks stored in ChromaDB."
            )
        else:
            print(
                f"[Ingestion Agent] "
                f"No text chunks found for {metadata.paper_id}."
            )

        return result

    except Exception as exc:
        print(
            f"[Ingestion Agent] "
            f"Failed to ingest {metadata.paper_id}: {exc}"
        )

        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[],
            raw_text=None,
        )