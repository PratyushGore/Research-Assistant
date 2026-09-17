from backend.agents.guided_input.agent import GuidedInputAgent
from backend.agents.guided_input.tiers import InputTier
from backend.schemas.schemas import (
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
    AcademicContentInfo,
)


def test_literature_survey_guided_input_flow():
    agent = GuidedInputAgent()
    request_id = "test-literature-1"

    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    ) == InputTier.TOPIC

    ok, error = agent.collect_topic(
        request_id,
        "AI in healthcare",
    )
    assert ok
    assert error == ""

    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    ) == InputTier.OUTPUT_TYPES

    ok, error = agent.collect_output_types(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    )
    assert ok
    assert error == ""

    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    ) == InputTier.COVER_INFO

    ok, error = agent.collect_cover_info(
        request_id,
        CoverInfo(
            title="AI in Healthcare",
            authors=["Sneha Konade"],
            institution="Pimpri Chinchwad University",
        ),
    )
    assert ok
    assert error == ""

    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    ) is None

    assert agent.is_complete(
        request_id,
        [OutputType.LITERATURE_SURVEY],
    )


def test_ppt_requires_presentation_info():
    agent = GuidedInputAgent()
    request_id = "test-ppt-1"

    agent.collect_topic(
        request_id,
        "Smart Queue Management System",
    )

    agent.collect_output_types(
        request_id,
        [OutputType.PPT],
    )

    agent.collect_cover_info(
        request_id,
        CoverInfo(
            title="Smart Queue Management System",
            authors=["Sneha Konade"],
        ),
    )

    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.PPT],
    ) == InputTier.PRESENTATION_INFO


def test_completed_tiers_are_not_asked_again():
    agent = GuidedInputAgent()
    request_id = "test-reuse-1"

    agent.collect_topic(
        request_id,
        "Multi-Agent AI Research Assistant",
    )

    agent.collect_output_types(
        request_id,
        [OutputType.PPT],
    )

    agent.collect_cover_info(
        request_id,
        CoverInfo(
            title="Multi-Agent AI Research Assistant",
            authors=["Sneha Konade"],
        ),
    )

    presentation_info = ProjectPresentationInfo(
        target_audience="College faculty",
        num_slides=10,
        presentation_tone="Formal",
        key_focus_areas=["Architecture", "Results"],
    )

    presentation_data = {
        "problem_statement": "Research workflows are time-consuming.",
        "tech_stack": "Python, React, LangGraph",
        "architecture_or_approach": "Multi-agent research pipeline",
        "own_results": "Prototype completed and tested.",
        "timeline": "January to September 2026",
    }

    ok, error = agent.collect_presentation_info(
        request_id,
        presentation_info,
        presentation_data,
    )

    assert ok
    assert error == ""

    # PPT is complete, so no tier should be requested again.
    assert agent.next_incomplete_tier(
        request_id,
        [OutputType.PPT],
    ) is None


def test_adding_research_paper_only_requires_academic_tier():
    agent = GuidedInputAgent()
    request_id = "test-output-change-1"

    agent.collect_topic(
        request_id,
        "AI-based research assistance",
    )

    agent.collect_output_types(
        request_id,
        [OutputType.PPT],
    )

    agent.collect_cover_info(
        request_id,
        CoverInfo(
            title="AI-based Research Assistance",
            authors=["Sneha Konade"],
        ),
    )

    presentation_info = ProjectPresentationInfo()

    presentation_data = {
        "problem_statement": "Research is difficult to organize.",
        "tech_stack": "Python, React",
        "architecture_or_approach": "Multi-agent architecture",
        "own_results": "Prototype tested.",
        "timeline": "2026",
    }

    agent.collect_presentation_info(
        request_id,
        presentation_info,
        presentation_data,
    )

    # Now the user adds Research Paper.
    # Existing completed tiers should be reused.
    assert agent.next_incomplete_tier(
        request_id,
        [
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
        ],
    ) == InputTier.ACADEMIC_INFO


def test_missing_ppt_project_content_is_rejected():
    agent = GuidedInputAgent()
    request_id = "test-ppt-validation-1"

    ok, error = agent.collect_presentation_info(
        request_id,
        ProjectPresentationInfo(),
        {},
    )

    assert not ok
    assert "Problem Statement" in error
    assert "Tech Stack" in error