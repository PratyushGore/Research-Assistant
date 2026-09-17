from backend.agents.composer.agent import ComposerAgent
from backend.schemas.schemas import (
    AcademicContentInfo,
    CitationResult,
    CoverInfo,
    FindingsPacket,
    GuidedInputBundle,
    OutputType,
    PaperSummary,
    ProjectPresentationInfo,
)


def sample_guided_input() -> GuidedInputBundle:
    return GuidedInputBundle(
        cover_info=CoverInfo(
            title="AI Research Assistant",
            subtitle="Multi-Agent System",
            authors=["Sneha Konade"],
            institution="Pimpri Chinchwad University",
            date="2026",
        ),
        project_presentation_info=ProjectPresentationInfo(
            problem_statement="Research work is time-consuming.",
            tech_stack=["Python", "LangGraph", "React"],
            own_architecture_summary="Multiple agents collaborate on research tasks.",
            own_results_summary="The system generates structured research outputs.",
        ),
        academic_content_info=AcademicContentInfo(
            methodology="Multi-agent architecture.",
            dataset_or_sample="Research papers related to AI.",
            tools_used=["Python", "LangGraph"],
            what_was_measured="Output quality.",
            key_results="Structured research outputs were generated.",
        ),
    )


def sample_findings() -> FindingsPacket:
    return FindingsPacket(
        topic="Multi-Agent AI Research Assistants",
        summaries=[
            PaperSummary(
                paper_id="paper-001",
                summary="Multi-agent systems divide complex tasks among specialized agents.",
                key_findings=[
                    "Task specialization supports workflow organization."
                ],
            )
        ],
    )


def sample_citations() -> CitationResult:
    return CitationResult(
        citation_style="apa",
        citations=[],
        bibliography=[
            "Smith, John. (2025). Multi-Agent Research Systems. AI Journal."
        ],
    )


def test_compose_literature_survey():
    agent = ComposerAgent()

    result = agent.compose(
        OutputType.LITERATURE_SURVEY,
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert result.output_type == OutputType.LITERATURE_SURVEY
    assert result.title == "AI Research Assistant"
    assert "## Abstract" in result.content
    assert "## Thematic Review" in result.content
    assert "## References" in result.content


def test_compose_executive_summary():
    agent = ComposerAgent()

    result = agent.compose(
        OutputType.EXECUTIVE_SUMMARY,
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert result.output_type == OutputType.EXECUTIVE_SUMMARY
    assert "## Cover" in result.content
    assert "## Overview" in result.content
    assert "## Key Findings" in result.content
    assert "## Implications" in result.content


def test_compose_ppt():
    agent = ComposerAgent()

    result = agent.compose(
        OutputType.PPT,
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert result.output_type == OutputType.PPT
    assert "## Title" in result.content
    assert "## Problem" in result.content
    assert "## Own Approach/Architecture" in result.content
    assert "## Own Results" in result.content


def test_compose_research_paper():
    agent = ComposerAgent()

    result = agent.compose(
        OutputType.RESEARCH_PAPER,
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert result.output_type == OutputType.RESEARCH_PAPER
    assert "## Abstract" in result.content
    assert "## Methodology" in result.content
    assert "## Results/Discussion" in result.content
    assert "## References" in result.content


def test_compose_tracks_citation_ids():
    from backend.schemas.schemas import FormattedCitation

    citation_result = CitationResult(
        citation_style="apa",
        citations=[
            FormattedCitation(
                citation_id="citation-paper-001",
                paper_id="paper-001",
                citation_style="apa",
                inline_marker="(Smith, 2025)",
                full_entry="Smith, John. (2025). Multi-Agent Research Systems.",
            )
        ],
        bibliography=[
            "Smith, John. (2025). Multi-Agent Research Systems."
        ],
    )

    agent = ComposerAgent()

    result = agent.compose(
        OutputType.LITERATURE_SURVEY,
        sample_guided_input(),
        sample_findings(),
        citation_result,
    )

    assert result.citations_used == ["citation-paper-001"]


def test_compose_research_paper_requires_academic_content():
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(title="Test Paper"),
    )

    agent = ComposerAgent()

    try:
        agent.compose(
            OutputType.RESEARCH_PAPER,
            guided_input,
            sample_findings(),
            sample_citations(),
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Academic Content Info is required" in str(exc)


def test_compose_ppt_requires_project_information():
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(title="Test Presentation"),
    )

    agent = ComposerAgent()

    try:
        agent.compose(
            OutputType.PPT,
            guided_input,
            sample_findings(),
            sample_citations(),
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Project Presentation Info is required" in str(exc)