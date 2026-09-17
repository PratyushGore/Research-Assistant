from backend.agents.guided_input.agent import GuidedInputAgent
from backend.agents.guided_input.tiers import InputTier
from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
)


def test_literature_survey_guided_input_flow():
    agent = GuidedInputAgent()
    session_id = "test-literature-1"

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        [],
    ) == InputTier.TOPIC

    ok, error, value = agent.collect_topic(
        session_id,
        "AI in healthcare",
    )
    assert ok
    assert error == ""
    assert value == "AI in healthcare"

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        ["topic"],
    ) == InputTier.OUTPUT_TYPES

    ok, error, value = agent.collect_output_types(
        session_id,
        [OutputType.LITERATURE_SURVEY],
    )
    assert ok
    assert error == ""
    assert value == [OutputType.LITERATURE_SURVEY]

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        ["topic", "output_types"],
    ) == InputTier.COVER_INFO

    cover_info = CoverInfo(
        title="AI in Healthcare",
        authors=["Sneha Konade"],
        institution="Pimpri Chinchwad University",
    )

    ok, error, value = agent.collect_cover_info(
        session_id,
        cover_info,
    )

    assert ok
    assert error == ""
    assert value == cover_info

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        ["topic", "output_types", "cover_info"],
    ) is None


def test_ppt_requires_presentation_info():
    agent = GuidedInputAgent()
    session_id = "test-ppt-1"

    completed = [
        "topic",
        "output_types",
        "cover_info",
    ]

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.PPT],
        completed,
    ) == InputTier.PRESENTATION_INFO


def test_completed_tiers_are_not_asked_again():
    agent = GuidedInputAgent()
    session_id = "test-reuse-1"

    completed = [
        "topic",
        "output_types",
        "cover_info",
        "presentation_info",
    ]

    assert agent.next_incomplete_tier(
        session_id,
        [OutputType.PPT],
        completed,
    ) is None


def test_adding_research_paper_only_requires_academic_tier():
    agent = GuidedInputAgent()
    session_id = "test-output-change-1"

    completed = [
        "topic",
        "output_types",
        "cover_info",
        "presentation_info",
    ]

    assert agent.next_incomplete_tier(
        session_id,
        [
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
        ],
        completed,
    ) == InputTier.ACADEMIC_INFO


def test_missing_ppt_project_content_is_rejected():
    agent = GuidedInputAgent()
    session_id = "test-ppt-validation-1"

    presentation_info = ProjectPresentationInfo(
        problem_statement="",
        tech_stack=[],
        own_architecture_summary="",
        own_results_summary="",
    )

    ok, error, value = agent.collect_presentation_info(
        session_id,
        presentation_info,
    )

    assert not ok
    assert "Problem statement" in error
    assert value is None


def test_valid_ppt_information_is_accepted():
    agent = GuidedInputAgent()
    session_id = "test-ppt-valid-1"

    presentation_info = ProjectPresentationInfo(
        problem_statement="Research workflows are time-consuming.",
        tech_stack=["Python", "React", "LangGraph"],
        own_architecture_summary="Multi-agent research pipeline.",
        own_results_summary="Prototype tested successfully.",
        project_timeline="2026",
    )

    ok, error, value = agent.collect_presentation_info(
        session_id,
        presentation_info,
    )

    assert ok
    assert error == ""
    assert value == presentation_info


def test_valid_academic_information_is_accepted():
    agent = GuidedInputAgent()
    session_id = "test-academic-valid-1"

    academic_info = AcademicContentInfo(
        methodology="Multi-agent research workflow",
        dataset_or_sample="Research papers",
        tools_used=["Python", "LangGraph"],
        what_was_measured="Answer accuracy",
        key_results="Verified outputs generated.",
        limitations="Limited evaluation dataset.",
    )

    ok, error, value = agent.collect_academic_info(
        session_id,
        academic_info,
    )

    assert ok
    assert error == ""
    assert value == academic_info


def test_orchestrator_owns_tier_memory():
    agent = GuidedInputAgent()
    session_id = "test-stateless-1"

    first = agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        [],
    )

    second = agent.next_incomplete_tier(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        [],
    )

    assert first == InputTier.TOPIC
    assert second == InputTier.TOPIC


def test_is_complete_uses_supplied_completed_tiers():
    agent = GuidedInputAgent()
    session_id = "test-complete-1"

    assert not agent.is_complete(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        [
            "topic",
            "output_types",
        ],
    )

    assert agent.is_complete(
        session_id,
        [OutputType.LITERATURE_SURVEY],
        [
            "topic",
            "output_types",
            "cover_info",
        ],
    )