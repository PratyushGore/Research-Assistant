from backend.agents.guided_input.mapper import build_guided_input_bundle
from backend.schemas.schemas import (
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
    AcademicContentInfo,
)


def test_mapper_builds_basic_bundle():
    bundle = build_guided_input_bundle(
        research_topic="AI in healthcare",
        output_types=[OutputType.LITERATURE_SURVEY],
        cover_info=CoverInfo(
            title="AI in Healthcare",
            authors=["Sneha Konade"],
            institution="Pimpri Chinchwad University",
        ),
    )

    assert bundle.research_topic == "AI in healthcare"
    assert bundle.output_types == [
        OutputType.LITERATURE_SURVEY
    ]
    assert bundle.cover_info.title == "AI in Healthcare"
    assert bundle.presentation_info is None
    assert bundle.academic_info is None


def test_mapper_builds_ppt_bundle_with_project_content():
    bundle = build_guided_input_bundle(
        research_topic="Smart Queue Management System",
        output_types=[OutputType.PPT],
        cover_info=CoverInfo(
            title="Smart Queue Management System",
            authors=["Sneha Konade"],
        ),
        presentation_info=ProjectPresentationInfo(
            target_audience="College faculty",
            num_slides=10,
            presentation_tone="Formal",
        ),
        presentation_data={
            "problem_statement": "Long waiting times in queues.",
            "tech_stack": "Python, React",
            "architecture_or_approach": "Queue prediction and management system",
            "own_results": "Prototype tested successfully.",
            "timeline": "2026",
        },
    )

    assert bundle.presentation_info is not None
    assert bundle.presentation_info.num_slides == 10

    assert bundle.user_notes is not None
    assert "[PRESENTATION PROJECT CONTENT]" in bundle.user_notes
    assert "Problem Statement: Long waiting times in queues." in bundle.user_notes
    assert "Tech Stack: Python, React" in bundle.user_notes


def test_mapper_builds_research_paper_bundle():
    bundle = build_guided_input_bundle(
        research_topic="AI-based research assistance",
        output_types=[OutputType.RESEARCH_PAPER],
        cover_info=CoverInfo(
            title="AI-based Research Assistance",
            authors=["Sneha Konade"],
        ),
        academic_info=AcademicContentInfo(
            citation_style="IEEE",
            keywords=["AI", "Research"],
        ),
        academic_data={
            "methodology_used": "Multi-agent architecture",
            "dataset_or_sample_details": "Research papers",
            "tools_or_instruments": "Python and LangGraph",
            "what_was_measured": "Answer accuracy",
            "key_results": "Improved verified research output",
            "limitations": "Limited evaluation dataset",
        },
    )

    assert bundle.academic_info is not None
    assert bundle.academic_info.citation_style == "IEEE"

    assert bundle.user_notes is not None
    assert "[ACADEMIC PROJECT CONTENT]" in bundle.user_notes
    assert "Methodology Used: Multi-agent architecture" in bundle.user_notes
    assert "Limitations: Limited evaluation dataset" in bundle.user_notes


def test_mapper_combines_ppt_and_academic_content():
    bundle = build_guided_input_bundle(
        research_topic="Multi-Agent AI Research Assistant",
        output_types=[
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
        ],
        cover_info=CoverInfo(
            title="Multi-Agent AI Research Assistant",
            authors=["Sneha Konade"],
        ),
        presentation_info=ProjectPresentationInfo(),
        academic_info=AcademicContentInfo(),
        presentation_data={
            "problem_statement": "Research workflows are time-consuming.",
            "tech_stack": "Python, React, LangGraph",
            "architecture_or_approach": "Multi-agent pipeline",
            "own_results": "Prototype tested.",
            "timeline": "2026",
        },
        academic_data={
            "methodology_used": "Multi-agent research workflow",
            "dataset_or_sample_details": "Research papers",
            "tools_or_instruments": "Python",
            "what_was_measured": "Output quality",
            "key_results": "Verified outputs generated.",
            "limitations": "Limited test set.",
        },
        user_notes="Generate concise academic content.",
    )

    assert bundle.user_notes is not None

    assert "[PRESENTATION PROJECT CONTENT]" in bundle.user_notes
    assert "[ACADEMIC PROJECT CONTENT]" in bundle.user_notes
    assert "[USER NOTES]" in bundle.user_notes

    assert "Problem Statement:" in bundle.user_notes
    assert "Methodology Used:" in bundle.user_notes