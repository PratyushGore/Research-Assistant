import io
import os
import re
import tempfile
import time
import requests
import fitz

from backend.schemas.schemas import PaperMetadata, Chunk, IngestionResult
from backend.vectorstore.store import add_chunks


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DOWNLOAD_TIMEOUT = 30

INGEST_MAX_PDF_MB = float(os.getenv("INGEST_MAX_PDF_MB", "2.0"))
INGEST_DOWNLOAD_TIMEOUT_S = float(os.getenv("INGEST_DOWNLOAD_TIMEOUT_S", "60"))
RA_PDF_CACHE_DIR = os.getenv("RA_PDF_CACHE_DIR", os.path.join(".cache", "pdf"))
DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB


def download_pdf(url: str) -> bytes:
    """Download a PDF from a URL."""
    match = re.search(r"arxiv\.org/abs/([^?#\s]+)", url)
    if match:
        paper_id = match.group(1).rstrip("/")
        url = f"https://arxiv.org/pdf/{paper_id}"

    cache_dir = os.getenv("RA_PDF_CACHE_DIR", RA_PDF_CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", url)
    cache_path = os.path.join(cache_dir, safe_filename)

    cached_file = None
    if os.path.exists(cache_path) and os.path.isfile(cache_path):
        cached_file = cache_path
    elif os.path.exists(cache_path + ".pdf") and os.path.isfile(cache_path + ".pdf"):
        cached_file = cache_path + ".pdf"

    if cached_file:
        try:
            with open(cached_file, "rb") as f:
                cached_bytes = f.read()
            if cached_bytes.startswith(b"%PDF"):
                return cached_bytes
        except Exception:
            pass

    max_mb = float(os.getenv("INGEST_MAX_PDF_MB", str(INGEST_MAX_PDF_MB)))
    timeout_s = float(os.getenv("INGEST_DOWNLOAD_TIMEOUT_S", str(INGEST_DOWNLOAD_TIMEOUT_S)))
    max_bytes = int(max_mb * 1024 * 1024)

    try:
        response = requests.get(
            url,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "Multi-Agent-Research-Assistant/1.0"},
            stream=True,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Download timed out after {timeout_s}s for URL {url}")

    # Check Content-Length header if present
    content_length = None
    if hasattr(response, "headers") and hasattr(response.headers, "get"):
        cl_header = response.headers.get("Content-Length")
        if cl_header is not None and isinstance(cl_header, (int, str)):
            try:
                content_length = int(cl_header)
            except ValueError:
                content_length = None

    if content_length is not None and content_length > max_bytes:
        cl_mb = content_length / (1024 * 1024)
        raise ValueError(
            f"PDF too large: {cl_mb:.1f} MB > {max_mb:.1f} MB for URL {url}"
        )

    # Read body in 64 KB chunks with hard deadline
    start_time = time.time()
    chunks = []
    total_bytes = 0

    if hasattr(response, "iter_content"):
        try:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                if not isinstance(chunk, (bytes, bytearray)):
                    break

                if time.time() - start_time > timeout_s:
                    raise TimeoutError(
                        f"Download timed out after {timeout_s}s for URL {url}"
                    )

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    dl_mb = total_bytes / (1024 * 1024)
                    raise ValueError(
                        f"PDF too large: {dl_mb:.1f} MB > {max_mb:.1f} MB for URL {url}"
                    )

                chunks.append(chunk)
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Download timed out after {timeout_s}s for URL {url}")

    # Fallback for mocks that only set mock_response.content = b"..."
    if not chunks and isinstance(getattr(response, "content", None), (bytes, bytearray)):
        chunk = response.content
        total_bytes = len(chunk)
        if total_bytes > max_bytes:
            dl_mb = total_bytes / (1024 * 1024)
            raise ValueError(
                f"PDF too large: {dl_mb:.1f} MB > {max_mb:.1f} MB for URL {url}"
            )
        chunks.append(chunk)

    pdf_bytes = b"".join(chunks)

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError(
            f"Downloaded content from {url} is not a valid PDF (does not start with %PDF)"
        )

    # Write cache only after validation succeeds, using temp file then os.replace
    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=cache_dir, prefix="tmp_pdf_")
        with os.fdopen(temp_fd, "wb") as f:
            f.write(pdf_bytes)
        os.replace(temp_path, cache_path)
    except Exception:
        if "temp_path" in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return pdf_bytes


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
    chunk_number = 0

    for page_number, page_text in pages:
        text = clean_text(page_text)

        if not text:
            continue

        start = 0

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

        if metadata.abstract:
            err_str = str(exc)
            if "too large" in err_str.lower():
                match = re.search(
                    r"(PDF too large:\s*[\d.]+\s*MB\s*>\s*[\d.]+\s*MB)",
                    err_str,
                    re.IGNORECASE,
                )
                reason = match.group(1).strip() if match else f"PDF too large: {err_str}"
            elif isinstance(exc, TimeoutError) or "timed out" in err_str.lower() or "timeout" in err_str.lower():
                reason = "timed out"
            else:
                reason = f"other error: {exc}"

            print(
                f"[Ingestion Agent] "
                f"Falling back to abstract for {metadata.paper_id} ({reason})."
            )
            fallback_chunk = Chunk(
                chunk_id=f"{metadata.paper_id}:chunk:0",
                paper_id=metadata.paper_id,
                text=metadata.abstract,
                section_heading=None,
                page_number=None,
            )
            stored_count = add_chunks([fallback_chunk])
            print(
                f"[Ingestion Agent] "
                f"{stored_count} chunks stored in ChromaDB."
            )
            return IngestionResult(
                paper_id=metadata.paper_id,
                metadata=metadata,
                chunks=[fallback_chunk],
                raw_text=metadata.abstract,
            )

        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[],
            raw_text=None,
        )