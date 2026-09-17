from backend.agents.citation.formatter import (
    format_apa,
    format_ieee,
    format_inline_marker,
    format_citation,
)
from backend.schemas.schemas import PaperMetadata


def sample_paper() -> PaperMetadata:
    return PaperMetadata(
        paper_id="paper-001",
        title="Artificial Intelligence in Healthcare",
        authors=["Smith, John", "Doe, Jane"],
        year=2025,
        url="https://example.com/paper",
        venue="Journal of AI Research",
        doi="10.1234/example",
    )


def test_format_apa():
    paper = sample_paper()

    result = format_apa(paper)

    assert "Smith, John & Doe, Jane" in result
    assert "(2025)" in result
    assert "Artificial Intelligence in Healthcare" in result
    assert "Journal of AI Research" in result
    assert "https://doi.org/10.1234/example" in result


def test_format_ieee():
    paper = sample_paper()

    result = format_ieee(paper)

    assert "Smith, John and Doe, Jane" in result
    assert '"Artificial Intelligence in Healthcare,"' in result
    assert "Journal of AI Research" in result
    assert "2025" in result
    assert "doi: 10.1234/example" in result


def test_apa_inline_marker():
    paper = sample_paper()

    result = format_inline_marker(
        paper,
        "apa",
        1,
    )

    assert result == "(Smith et al., 2025)"


def test_ieee_inline_marker():
    paper = sample_paper()

    result = format_inline_marker(
        paper,
        "ieee",
        1,
    )

    assert result == "[1]"


def test_format_complete_citation():
    paper = sample_paper()

    result = format_citation(
        paper,
        "ieee",
        1,
    )

    assert result.citation_id == "citation-paper-001"
    assert result.paper_id == "paper-001"
    assert result.citation_style == "ieee"
    assert result.inline_marker == "[1]"
    assert "Artificial Intelligence in Healthcare" in result.full_entry


def test_unsupported_style():
    paper = sample_paper()

    try:
        format_citation(paper, "mla", 1)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unsupported citation style" in str(exc)