import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Optional
import xml.etree.ElementTree as ET

import requests

from backend.schemas.schemas import PaperMetadata, SearchResult


# ============================================================
# API ENDPOINTS
# ============================================================

ARXIV_API_URL = "https://export.arxiv.org/api/query"

SEMANTIC_SCHOLAR_API_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

CORE_API_URL = "https://api.core.ac.uk/v3/search/works"


# ============================================================
# ARXIV SEARCH
# ============================================================

def search_arxiv(
    query: str,
    limit: int = 5,
) -> list[PaperMetadata]:
    """Search arXiv for research papers."""

    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=all:{query}"
        f"&start=0"
        f"&max_results={limit}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    root = ET.fromstring(response.text)

    namespace = {
        "atom": "http://www.w3.org/2005/Atom"
    }

    papers = []

    for entry in root.findall("atom:entry", namespace):

        title = entry.findtext(
            "atom:title",
            default="",
            namespaces=namespace,
        )

        abstract = entry.findtext(
            "atom:summary",
            default="",
            namespaces=namespace,
        )

        published = entry.findtext(
            "atom:published",
            default="",
            namespaces=namespace,
        )

        paper_url = entry.findtext(
            "atom:id",
            default="",
            namespaces=namespace,
        )

        authors = []

        for author in entry.findall(
            "atom:author",
            namespace,
        ):
            name = author.findtext(
                "atom:name",
                default="",
                namespaces=namespace,
            )

            if name:
                authors.append(name.strip())

        year = None

        if published:
            try:
                year = int(published[:4])
            except ValueError:
                year = None

        paper_id = paper_url.rstrip("/").split("/")[-1]

        papers.append(
            PaperMetadata(
                paper_id=f"arxiv:{paper_id}",
                title=" ".join(title.split()),
                authors=authors,
                abstract=" ".join(abstract.split()) or None,
                year=year,
                url=paper_url or None,
                venue="arXiv",
            )
        )

    return papers


# ============================================================
# SEMANTIC SCHOLAR SEARCH
# ============================================================

def search_semantic_scholar(
    query: str,
    limit: int = 5,
) -> list[PaperMetadata]:
    """Search Semantic Scholar."""

    params = {
        "query": query,
        "limit": limit,
        "fields": (
            "paperId,title,authors,abstract,year,"
            "url,venue,externalIds"
        ),
    }

    headers = {
        "User-Agent": "Multi-Agent-Research-Assistant/1.0",
        "Accept": "application/json",
    }

    api_key = os.getenv("S2_API_KEY")

    if api_key:
        headers["x-api-key"] = api_key

    try:
        response = requests.get(
            SEMANTIC_SCHOLAR_API_URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        # Semantic Scholar rate limit
        if response.status_code == 429:
            print(
                "[Search Agent] Semantic Scholar rate limit "
                "reached. Skipping this source for now."
            )
            return []

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as exc:
        print(
            f"[Search Agent] Semantic Scholar request failed: "
            f"{exc}"
        )
        return []

    papers = []

    for item in data.get("data", []):

        paper_id = item.get("paperId")

        if not paper_id:
            continue

        authors = [
            author.get("name", "").strip()
            for author in item.get("authors", [])
            if author.get("name")
        ]

        external_ids = item.get("externalIds") or {}

        papers.append(
            PaperMetadata(
                paper_id=f"s2:{paper_id}",
                title=(item.get("title") or "").strip(),
                authors=authors,
                abstract=item.get("abstract"),
                year=item.get("year"),
                url=item.get("url"),
                venue=item.get("venue"),
                doi=external_ids.get("DOI"),
            )
        )

    return papers


# ============================================================
# CORE SEARCH
# ============================================================

def search_core(
    query: str,
    limit: int = 5,
) -> list[PaperMetadata]:
    """Search CORE if an API key is configured."""

    api_key = os.getenv("CORE_API_KEY")

    if not api_key:
        print(
            "[Search Agent] CORE skipped: "
            "CORE_API_KEY is not configured."
        )
        return []

    params = {
        "q": query,
        "limit": limit,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    response = requests.get(
        CORE_API_URL,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    papers = []

    for item in data.get("results", []):

        paper_id = item.get("id")

        if not paper_id:
            continue

        authors = []

        for author in item.get("authors", []) or []:

            if isinstance(author, dict):
                name = author.get("name")
            else:
                name = str(author)

            if name:
                authors.append(name.strip())

        papers.append(
            PaperMetadata(
                paper_id=f"core:{paper_id}",
                title=(item.get("title") or "").strip(),
                authors=authors,
                abstract=item.get("abstract"),
                year=item.get("yearPublished"),
                url=item.get("downloadUrl"),
                venue=item.get("publisher"),
                doi=item.get("doi"),
            )
        )

    return papers


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def _deduplicate_papers(
    papers: list[PaperMetadata],
) -> list[PaperMetadata]:
    """Remove duplicate papers."""

    unique_papers = []
    seen = set()

    for paper in papers:

        if paper.doi:
            key = f"doi:{paper.doi.lower()}"

        elif paper.url:
            key = f"url:{paper.url.lower().rstrip('/')}"

        else:
            key = f"title:{paper.title.lower().strip()}"

        if key in seen:
            continue

        seen.add(key)
        unique_papers.append(paper)

    return unique_papers


# ============================================================
# MAIN SEARCH FUNCTION
# ============================================================

def search_papers(
    query: str,
    max_results_per_source: int = 5,
) -> SearchResult:
    """
    Search all configured academic sources.

    Sources:
    1. arXiv
    2. Semantic Scholar
    3. CORE
    """

    if not query or not query.strip():
        return SearchResult(
            query=query,
            papers=[],
            total_results=0,
        )

    all_papers = []

    sources = [
        ("arXiv", search_arxiv),
        ("Semantic Scholar", search_semantic_scholar),
        ("CORE", search_core),
    ]

    for source_name, search_function in sources:

        try:

            results = search_function(
                query.strip(),
                max_results_per_source,
            )

            all_papers.extend(results)

            print(
                f"[Search Agent] {source_name}: "
                f"{len(results)} papers found."
            )

        except Exception as exc:

            print(
                f"[Search Agent] {source_name} search failed: "
                f"{exc}"
            )

    unique_papers = _deduplicate_papers(all_papers)

    return SearchResult(
        query=query.strip(),
        papers=unique_papers,
        total_results=len(unique_papers),
    )


# ============================================================
# DETERMINISTIC POOL SEARCH (PAGED, ORDERED, CACHED)
# ============================================================

_last_arxiv_request_time: float = 0.0


def _normalize_topic(query: str) -> str:
    """Normalize topic to lowercase with collapsed whitespace."""
    return " ".join(query.lower().strip().split())


def _normalize_title(title: str) -> str:
    """Normalize title to lowercase with punctuation stripped and collapsed whitespace."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(cleaned.strip().split())


def _normalize_url(url: Optional[str]) -> Optional[str]:
    """Normalize URL by stripping whitespace, trailing slashes, and lowercasing."""
    if not url:
        return None
    return url.strip().lower().rstrip("/")


def _deduplicate_papers_pool(
    papers: list[PaperMetadata],
    existing_pool: Optional[list[PaperMetadata]] = None,
) -> list[PaperMetadata]:
    """
    Deduplicate papers by doi/url and by normalized title (lowercase, punctuation stripped).
    Preserves existing_pool items and appends only new unique papers.
    """
    unique_papers = list(existing_pool) if existing_pool else []
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for p in unique_papers:
        if p.doi:
            seen_dois.add(p.doi.strip().lower())
        if p.url:
            norm_u = _normalize_url(p.url)
            if norm_u:
                seen_urls.add(norm_u)
        if p.title:
            norm_t = _normalize_title(p.title)
            if norm_t:
                seen_titles.add(norm_t)

    for paper in papers:
        doi_norm = paper.doi.strip().lower() if paper.doi else None
        url_norm = _normalize_url(paper.url) if paper.url else None
        title_norm = _normalize_title(paper.title) if paper.title else None

        is_dup = False
        if doi_norm and doi_norm in seen_dois:
            is_dup = True
        elif url_norm and url_norm in seen_urls:
            is_dup = True
        elif title_norm and title_norm in seen_titles:
            is_dup = True

        if is_dup:
            continue

        if doi_norm:
            seen_dois.add(doi_norm)
        if url_norm:
            seen_urls.add(url_norm)
        if title_norm:
            seen_titles.add(title_norm)

        unique_papers.append(paper)

    return unique_papers


def _parse_arxiv_atom(xml_text: str) -> list[PaperMetadata]:
    """Parse arXiv Atom XML response into PaperMetadata objects."""
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        print(f"[Search Agent] Failed to parse arXiv XML: {exc}")
        return []

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    papers = []

    for entry in root.findall("atom:entry", namespace):
        title = entry.findtext("atom:title", default="", namespaces=namespace)
        abstract = entry.findtext("atom:summary", default="", namespaces=namespace)
        published = entry.findtext("atom:published", default="", namespaces=namespace)
        paper_url = entry.findtext("atom:id", default="", namespaces=namespace)

        authors = []
        for author in entry.findall("atom:author", namespace):
            name = author.findtext("atom:name", default="", namespaces=namespace)
            if name:
                authors.append(name.strip())

        year = None
        if published:
            try:
                year = int(published[:4])
            except ValueError:
                year = None

        paper_id = paper_url.rstrip("/").split("/")[-1]

        # Extract DOI if present
        doi = None
        doi_elem = entry.findtext("{http://arxiv.org/schemas/atom}doi", default="")
        if doi_elem:
            doi = doi_elem.strip()

        # Check for direct PDF link
        pdf_url = None
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href")
                break

        url_to_use = pdf_url or paper_url or None

        papers.append(
            PaperMetadata(
                paper_id=f"arxiv:{paper_id}",
                title=" ".join(title.split()),
                authors=authors,
                abstract=" ".join(abstract.split()) or None,
                year=year,
                url=url_to_use,
                venue="arXiv",
                doi=doi,
            )
        )

    return papers


def _fetch_arxiv_page_with_retry(
    query: str,
    start: int = 0,
    limit: int = 25,
) -> list[PaperMetadata]:
    """
    Fetch a page of arXiv results with polite delay (>= 3s between requests)
    and retry with backoff (up to 3 tries) on 429, 5xx, or timeout.
    """
    global _last_arxiv_request_time
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=all:{query}"
        f"&start={start}"
        f"&max_results={limit}"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    max_retries = 3
    backoff_delays = [3.0, 6.0, 12.0]

    for attempt in range(max_retries):
        if _last_arxiv_request_time > 0:
            elapsed = time.time() - _last_arxiv_request_time
            if elapsed < 3.0:
                time.sleep(3.0 - elapsed)

        try:
            response = requests.get(url, headers=headers, timeout=30)
            _last_arxiv_request_time = time.time()

            if response.status_code == 429 or 500 <= response.status_code < 600:
                print(
                    f"[Search Agent] arXiv HTTP {response.status_code} "
                    f"(attempt {attempt + 1}/{max_retries})."
                )
                if attempt < max_retries - 1:
                    time.sleep(backoff_delays[attempt])
                    continue
                else:
                    print(f"[Search Agent] arXiv retries exhausted.")
                    return []

            response.raise_for_status()
            return _parse_arxiv_atom(response.text)

        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
            _last_arxiv_request_time = time.time()
            print(
                f"[Search Agent] arXiv request failed ({exc}) "
                f"(attempt {attempt + 1}/{max_retries})."
            )
            if attempt < max_retries - 1:
                time.sleep(backoff_delays[attempt])
                continue
            else:
                print(f"[Search Agent] arXiv retries exhausted.")
                return []
        except Exception as exc:
            _last_arxiv_request_time = time.time()
            print(f"[Search Agent] arXiv unexpected error: {exc}")
            return []

    return []


def get_cache_dir() -> Path:
    """Return the search cache directory path, ensuring it exists."""
    env_dir = os.getenv("SEARCH_CACHE_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = Path(__file__).resolve().parents[3] / ".cache" / "search"
    p.mkdir(parents=True, exist_ok=True)
    return p


CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _load_cached_pool(norm_topic: str) -> Optional[dict[str, Any]]:
    """Load cached search candidate pool if present and unexpired."""
    sha1 = hashlib.sha1(norm_topic.encode("utf-8")).hexdigest()
    cache_file = get_cache_dir() / f"{sha1}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        created_at = data.get("created_at", 0)
        if time.time() - created_at > CACHE_TTL_SECONDS:
            return None
        return data
    except Exception as exc:
        print(f"[Search Agent] Failed to read cache: {exc}")
        return None


def _save_cached_pool(
    norm_topic: str,
    papers: list[PaperMetadata],
    exhausted: bool,
    arxiv_offset: int,
) -> None:
    """Atomically persist candidate pool to cache."""
    sha1 = hashlib.sha1(norm_topic.encode("utf-8")).hexdigest()
    cache_dir = get_cache_dir()
    cache_file = cache_dir / f"{sha1}.json"
    temp_file = cache_dir / f"{sha1}_{os.getpid()}_{time.time_ns()}.tmp"

    data = {
        "topic": norm_topic,
        "created_at": time.time(),
        "exhausted": exhausted,
        "arxiv_offset": arxiv_offset,
        "papers": [p.model_dump() for p in papers],
    }

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, cache_file)
    except Exception as exc:
        print(f"[Search Agent] Failed to write cache atomically: {exc}")
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass


def search_papers_pool(
    query: str,
    target: int = 8,
) -> SearchResult:
    """
    Build an ORDERED candidate pool of up to max(target*2, 20) (cap 40) unique papers:
    - arXiv first with paging (start offset, page size 25), polite delay of >= 3s,
      retry with backoff (up to 3 tries) on 429/5xx/timeout.
    - Semantic Scholar then CORE only to top up when unique pool is still smaller than needed.
    - Dedupe by doi/url and normalized title; deterministic stable ordering.
    - Persist pool per normalized topic in .cache/search/<sha1>.json with created_at,
      flag 'exhausted', TTL 30 days, atomic write.
    - Later requests reuse cached pool with zero network calls when holding enough or exhausted.
    """
    if not query or not query.strip():
        return SearchResult(query=query, papers=[], total_results=0)

    norm_topic = _normalize_topic(query)
    needed_pool_size = min(max(target * 2, 20), 40)

    cached_data = _load_cached_pool(norm_topic)
    if cached_data is not None:
        cached_papers = [PaperMetadata(**p) for p in cached_data.get("papers", [])]
        is_exhausted = bool(cached_data.get("exhausted", False))
        arxiv_offset = int(cached_data.get("arxiv_offset", len(cached_papers)))

        if len(cached_papers) >= needed_pool_size or is_exhausted:
            print(
                f"[Search Agent] Cache hit for '{norm_topic}': "
                f"{len(cached_papers)} candidates available (exhausted={is_exhausted}). Zero network calls."
            )
            return SearchResult(
                query=query.strip(),
                papers=cached_papers[:needed_pool_size],
                total_results=len(cached_papers[:needed_pool_size]),
            )
        pool = list(cached_papers)
    else:
        pool = []
        is_exhausted = False
        arxiv_offset = 0

    # 1. arXiv paging
    arxiv_exhausted = False
    while len(pool) < needed_pool_size and not arxiv_exhausted:
        page_size = 25
        arxiv_results = _fetch_arxiv_page_with_retry(
            query.strip(),
            start=arxiv_offset,
            limit=page_size,
        )
        arxiv_offset += page_size

        if not arxiv_results:
            arxiv_exhausted = True
            break

        prev_len = len(pool)
        pool = _deduplicate_papers_pool(arxiv_results, existing_pool=pool)

        if len(arxiv_results) < page_size:
            arxiv_exhausted = True
            break

        if len(pool) == prev_len:
            arxiv_exhausted = True
            break

    # 2. Semantic Scholar top up (only if needed)
    if len(pool) < needed_pool_size:
        print(
            f"[Search Agent] Topping up with Semantic Scholar "
            f"(pool has {len(pool)}/{needed_pool_size})..."
        )
        try:
            s2_limit = min(needed_pool_size - len(pool) + 5, 20)
            s2_results = search_semantic_scholar(query.strip(), limit=s2_limit)
            pool = _deduplicate_papers_pool(s2_results, existing_pool=pool)
        except Exception as exc:
            print(f"[Search Agent] Semantic Scholar top up failed (skipped): {exc}")

    # 3. CORE top up (only if needed)
    if len(pool) < needed_pool_size:
        print(
            f"[Search Agent] Topping up with CORE "
            f"(pool has {len(pool)}/{needed_pool_size})..."
        )
        try:
            core_limit = min(needed_pool_size - len(pool) + 5, 20)
            core_results = search_core(query.strip(), limit=core_limit)
            pool = _deduplicate_papers_pool(core_results, existing_pool=pool)
        except Exception as exc:
            print(f"[Search Agent] CORE top up failed (skipped): {exc}")

    exhausted = len(pool) < needed_pool_size

    _save_cached_pool(norm_topic, pool, exhausted=exhausted, arxiv_offset=arxiv_offset)

    return SearchResult(
        query=query.strip(),
        papers=pool[:needed_pool_size],
        total_results=len(pool[:needed_pool_size]),
    )