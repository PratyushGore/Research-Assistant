from backend.agents.composer.generator import (
    generate_executive_summary,
    generate_literature_survey,
    generate_ppt,
    generate_research_paper,
)
from backend.schemas.schemas import (
    CitationResult,
    CoverInfo,
    FindingsPacket,
    GuidedInputBundle,
    PaperSummary,
    ProjectPresentationInfo,
    AcademicContentInfo,
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
            problem_statement="Research work is time-consuming and difficult to organize.",
            tech_stack=["Python", "LangGraph", "React"],
            own_architecture_summary="Multiple specialized agents collaborate to support research.",
            own_results_summary="The system generates structured research outputs.",
        ),
        academic_content_info=AcademicContentInfo(
            methodology="Multi-agent architecture with retrieval and verification.",
            dataset_or_sample="Research papers related to AI.",
            tools_used=["Python", "LangGraph", "ChromaDB"],
            what_was_measured="Output quality and citation correctness.",
            key_results="The system produces structured and traceable research outputs.",
            limitations="LLM output quality depends on available source material.",
        ),
    )


def sample_findings() -> FindingsPacket:
    return FindingsPacket(
        topic="Multi-Agent AI Research Assistants",
        summaries=[
            PaperSummary(
                paper_id="paper-001",
                summary="Multi-agent systems can divide complex research tasks among specialized agents.",
                key_findings=[
                    "Task specialization can improve workflow organization.",
                    "Agent collaboration can support complex research tasks.",
                ],
            ),
            PaperSummary(
                paper_id="paper-002",
                summary="Retrieval-based systems can help ground generated responses in source material.",
                key_findings=[
                    "Source grounding improves traceability.",
                ],
            ),
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


def test_generate_literature_survey():
    sections = generate_literature_survey(
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert "Abstract" in sections
    assert "Introduction" in sections
    assert "Thematic Review" in sections
    assert "Synthesis" in sections
    assert "Conclusion" in sections
    assert "References" in sections

    assert "Multi-Agent AI Research Assistants" in sections["Introduction"]
    assert "paper-001" in sections["Thematic Review"]


def test_generate_executive_summary():
    sections = generate_executive_summary(
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert "Cover" in sections
    assert "Overview" in sections
    assert "Key Findings" in sections
    assert "Implications" in sections

    assert "AI Research Assistant" in sections["Cover"]
    assert "paper-001" in sections["Key Findings"]


def test_generate_ppt():
    sections = generate_ppt(
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert "Title" in sections
    assert "Problem" in sections
    assert "Literature Findings" in sections
    assert "Own Approach/Architecture" in sections
    assert "Own Results" in sections
    assert "Comparison" in sections
    assert "Conclusion" in sections

    assert "Research work is time-consuming" in sections["Problem"]
    assert "Multiple specialized agents" in sections["Own Approach/Architecture"]


def test_generate_research_paper():
    sections = generate_research_paper(
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert "Abstract" in sections
    assert "Introduction" in sections
    assert "Literature Review" in sections
    assert "Methodology" in sections
    assert "Results/Discussion" in sections
    assert "Conclusion" in sections
    assert "References" in sections

    assert "Multi-agent architecture" in sections["Methodology"]
    assert "structured and traceable" in sections["Results/Discussion"]


def test_ppt_requires_project_presentation_info():
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(title="Test Project"),
    )

    try:
        generate_ppt(
            guided_input,
            sample_findings(),
            sample_citations(),
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Project Presentation Info is required" in str(exc)


def test_research_paper_requires_academic_content_info():
    guided_input = GuidedInputBundle(
        cover_info=CoverInfo(title="Test Paper"),
    )

    try:
        generate_research_paper(
            guided_input,
            sample_findings(),
            sample_citations(),
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Academic Content Info is required" in str(exc)


def test_research_paper_uses_provided_methodology_and_results():
    sections = generate_research_paper(
        sample_guided_input(),
        sample_findings(),
        sample_citations(),
    )

    assert (
        "Multi-agent architecture with retrieval and verification."
        in sections["Methodology"]
    )
    assert (
        "The system produces structured and traceable research outputs."
        in sections["Results/Discussion"]
    )