import os
import requests
import xml.etree.ElementTree as ET

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