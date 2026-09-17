from backend.schemas.schemas import (
    CitationResult,
    FormattedCitation,
    PaperMetadata,
)

from .formatter import format_citation


class CitationAgent:
    """
    Citation Agent.

    Converts paper metadata into formatted citations and
    a bibliography using deterministic citation formatting.
    """

    SUPPORTED_STYLES = {"apa", "ieee"}

    def generate_citations(
        self,
        papers: list[PaperMetadata],
        citation_style: str = "apa",
    ) -> CitationResult:
        """
        Generate citations for a list of papers.

        The same paper is formatted deterministically and receives
        a stable citation ID based on its paper_id.
        """

        style = citation_style.strip().lower()

        if style not in self.SUPPORTED_STYLES:
            raise ValueError(
                f"Unsupported citation style: {citation_style}"
            )

        citations: list[FormattedCitation] = []

        for index, paper in enumerate(papers, start=1):
            citation = format_citation(
                paper=paper,
                citation_style=style,
                index=index,
            )
            citations.append(citation)

        bibliography = [
            citation.full_entry
            for citation in citations
        ]

        return CitationResult(
            citation_style=style,
            citations=citations,
            bibliography=bibliography,
        )


citation_agent = CitationAgent()