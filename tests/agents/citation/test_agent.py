from backend.agents.citation.agent import CitationAgent
from backend.schemas.schemas import PaperMetadata


def sample_papers() -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id="paper-001",
            title="Artificial Intelligence in Healthcare",
            authors=["Smith, John", "Doe, Jane"],
            year=2025,
            venue="Journal of AI Research",
            doi="10.1234/example",
        ),
        PaperMetadata(
            paper_id="paper-002",
            title="Deep Learning for Medical Diagnosis",
            authors=["Brown, Alice"],
            year=2024,
            venue="Medical AI Journal",
        ),
    ]


def test_agent_generates_apa_citations():
    agent = CitationAgent()

    result = agent.generate_citations(
        sample_papers(),
        citation_style="apa",
    )

    assert result.citation_style == "apa"
    assert len(result.citations) == 2
    assert len(result.bibliography) == 2

    assert result.citations[0].paper_id == "paper-001"
    assert result.citations[0].inline_marker == "(Smith et al., 2025)"


def test_agent_generates_ieee_citations():
    agent = CitationAgent()

    result = agent.generate_citations(
        sample_papers(),
        citation_style="ieee",
    )

    assert result.citation_style == "ieee"
    assert len(result.citations) == 2

    assert result.citations[0].inline_marker == "[1]"
    assert result.citations[1].inline_marker == "[2]"


def test_agent_creates_bibliography():
    agent = CitationAgent()

    result = agent.generate_citations(
        sample_papers(),
        citation_style="apa",
    )

    assert len(result.bibliography) == 2
    assert "Artificial Intelligence in Healthcare" in result.bibliography[0]
    assert "Deep Learning for Medical Diagnosis" in result.bibliography[1]


def test_agent_handles_empty_paper_list():
    agent = CitationAgent()

    result = agent.generate_citations(
        [],
        citation_style="apa",
    )

    assert result.citation_style == "apa"
    assert result.citations == []
    assert result.bibliography == []


def test_agent_rejects_unsupported_style():
    agent = CitationAgent()

    try:
        agent.generate_citations(
            sample_papers(),
            citation_style="mla",
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unsupported citation style" in str(exc)