from backend.agents.guided_input.mapper import (
    build_guided_input_bundle,
)
from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
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

    assert bundle.cover_info is not None
    assert bundle.cover_info.title == "AI in Healthcare"

    assert bundle.project_presentation_info is None
    assert bundle.academic_content_info is None


def test_mapper_builds_ppt_bundle():
    presentation_info = ProjectPresentationInfo(
        problem_statement="Long waiting times in queues.",
        tech_stack=["Python", "React"],
        own_architecture_summary=(
            "Queue prediction and management system."
        ),
        own_results_summary=(
            "Prototype tested successfully."
        ),
        project_timeline="2026",
    )

    bundle = build_guided_input_bundle(
        research_topic="Smart Queue Management System",
        output_types=[OutputType.PPT],
        cover_info=CoverInfo(
            title="Smart Queue Management System",
            authors=["Sneha Konade"],
        ),
        presentation_info=presentation_info,
    )

    assert bundle.project_presentation_info is not None
    assert (
        bundle.project_presentation_info.problem_statement
        == "Long waiting times in queues."
    )

    assert (
        bundle.project_presentation_info.tech_stack
        == ["Python", "React"]
    )

    assert (
        bundle.project_presentation_info.own_architecture_summary
        == "Queue prediction and management system."
    )


def test_mapper_builds_research_paper_bundle():
    academic_info = AcademicContentInfo(
        methodology="Multi-agent architecture",
        dataset_or_sample="Research papers",
        tools_used=["Python", "LangGraph"],
        what_was_measured="Answer accuracy",
        key_results="Improved verified research output",
        limitations="Limited evaluation dataset",
    )

    bundle = build_guided_input_bundle(
        research_topic="AI-based research assistance",
        output_types=[OutputType.RESEARCH_PAPER],
        cover_info=CoverInfo(
            title="AI-based Research Assistance",
            authors=["Sneha Konade"],
        ),
        academic_info=academic_info,
    )

    assert bundle.academic_content_info is not None

    assert (
        bundle.academic_content_info.methodology
        == "Multi-agent architecture"
    )

    assert (
        bundle.academic_content_info.dataset_or_sample
        == "Research papers"
    )

    assert (
        bundle.academic_content_info.tools_used
        == ["Python", "LangGraph"]
    )


def test_mapper_builds_combined_ppt_and_research_paper_bundle():
    presentation_info = ProjectPresentationInfo(
        problem_statement=(
            "Research workflows are time-consuming."
        ),
        tech_stack=[
            "Python",
            "React",
            "LangGraph",
        ],
        own_architecture_summary="Multi-agent pipeline",
        own_results_summary="Prototype tested.",
        project_timeline="2026",
    )

    academic_info = AcademicContentInfo(
        methodology="Multi-agent research workflow",
        dataset_or_sample="Research papers",
        tools_used=["Python"],
        what_was_measured="Output quality",
        key_results="Verified outputs generated.",
        limitations="Limited test set.",
    )

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
        presentation_info=presentation_info,
        academic_info=academic_info,
        user_notes="Generate concise academic content.",
    )

    assert bundle.project_presentation_info is not None
    assert bundle.academic_content_info is not None

    assert (
        bundle.project_presentation_info
        .own_results_summary
        == "Prototype tested."
    )

    assert (
        bundle.academic_content_info
        .key_results
        == "Verified outputs generated."
    )
