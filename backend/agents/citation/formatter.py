from backend.schemas.schemas import FormattedCitation, PaperMetadata


def _format_authors_apa(authors: list[str]) -> str:
    if not authors:
        return "Unknown Author"

    if len(authors) == 1:
        return authors[0]

    if len(authors) == 2:
        return f"{authors[0]} & {authors[1]}"

    return f"{authors[0]} et al."


def _format_authors_ieee(authors: list[str]) -> str:
    if not authors:
        return "Unknown Author"

    if len(authors) == 1:
        return authors[0]

    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"

    return f"{authors[0]} et al."


def format_apa(paper: PaperMetadata) -> str:
    """Create a compact APA-style reference entry."""
    authors = _format_authors_apa(paper.authors)
    year = f"({paper.year})" if paper.year else "(n.d.)"

    entry = f"{authors}. {year}. {paper.title}."

    if paper.venue:
        entry += f" {paper.venue}."

    if paper.doi:
        entry += f" https://doi.org/{paper.doi}"
    elif paper.url:
        entry += f" {paper.url}"

    return entry


def format_ieee(paper: PaperMetadata) -> str:
    """Create a compact IEEE-style reference entry."""
    authors = _format_authors_ieee(paper.authors)

    entry = f"{authors}, \"{paper.title},\""

    if paper.venue:
        entry += f" {paper.venue},"

    if paper.year:
        entry += f" {paper.year}."

    if paper.doi:
        entry += f" doi: {paper.doi}"
    elif paper.url:
        entry += f" [Online]. Available: {paper.url}"

    return entry


def format_inline_marker(
    paper: PaperMetadata,
    citation_style: str,
    index: int,
) -> str:
    """Create an inline citation marker."""
    style = citation_style.lower()

    if style == "ieee":
        return f"[{index}]"

    # APA and other author-year styles.
    if paper.authors:
        first_author = paper.authors[0].split(",")[0].strip()
    else:
        first_author = "Unknown Author"

    if len(paper.authors) > 1:
        author_text = f"{first_author} et al."
    else:
        author_text = first_author

    year = str(paper.year) if paper.year else "n.d."

    return f"({author_text}, {year})"


def format_citation(
    paper: PaperMetadata,
    citation_style: str,
    index: int,
) -> FormattedCitation:
    """Build a complete formatted citation."""
    style = citation_style.lower()

    if style == "apa":
        full_entry = format_apa(paper)
    elif style == "ieee":
        full_entry = format_ieee(paper)
    else:
        raise ValueError(
            f"Unsupported citation style: {citation_style}"
        )

    return FormattedCitation(
        citation_id=f"citation-{paper.paper_id}",
        paper_id=paper.paper_id,
        citation_style=style,
        inline_marker=format_inline_marker(
            paper,
            style,
            index,
        ),
        full_entry=full_entry,
    )