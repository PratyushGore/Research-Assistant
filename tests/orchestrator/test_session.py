"""
Tests for the Orchestrator SessionStore.
"""

from concurrent.futures import ThreadPoolExecutor
import pytest

from backend.agents.guided_input.tiers import InputTier
from backend.orchestrator.session import (
    InvalidSessionStateError,
    SessionNotFoundError,
    SessionStatus,
    SessionStore,
    get_bundle,
    get_research_results,
    get_session,
    select_outputs,
    start_research,
    store_research_results,
    submit_tier,
)
from backend.schemas.schemas import (
    AcademicContentInfo,
    CitationResult,
    CoverInfo,
    FindingsPacket,
    FormattedCitation,
    OutputType,
    PaperSummary,
    ProjectPresentationInfo,
)


@pytest.fixture
def sample_findings():
    return FindingsPacket(
        topic="RAG Architecture",
        summaries=[
            PaperSummary(
                paper_id="p1",
                summary="Vector indexing with dense embeddings.",
                key_findings=["Improves factual recall by 35%"],
            )
        ],
        claims=[],
        contradictions=[],
        cross_paper_synthesis="Cross paper synthesis text.",
    )


@pytest.fixture
def sample_citations():
    return CitationResult(
        citation_style="apa",
        citations=[
            FormattedCitation(
                citation_id="cit1",
                paper_id="p1",
                citation_style="apa",
                inline_marker="(Lewis et al., 2020)",
                full_entry="Lewis, P. et al. (2020). Retrieval-Augmented Generation.",
            )
        ],
        bibliography=["Lewis, P. et al. (2020). Retrieval-Augmented Generation."],
    )


def test_full_new_sequence_end_to_end(sample_findings, sample_citations):
    """
    Test the full sequence:
    start_research -> store_research_results -> get_research_results ->
    select_outputs -> submit_tier -> get_bundle.
    """
    store = SessionStore()
    sid = store.start_research("RAG Architecture")

    assert sid is not None
    assert len(sid) > 0

    record = store.get_session(sid)
    assert record["session_id"] == sid
    assert record["research_topic"] == "RAG Architecture"
    assert record["topic"] == "RAG Architecture"
    assert record["status"] == SessionStatus.RESEARCHING.value
    assert record["findings"] is None
    assert record["citations"] is None

    # Store research results
    store.store_research_results(sid, sample_findings, sample_citations)
    record = store.get_session(sid)
    assert record["status"] == SessionStatus.RESEARCH_DONE.value
    assert record["findings"] == sample_findings
    assert record["citations"] == sample_citations

    # Get research results
    findings, citations = store.get_research_results(sid)
    assert findings == sample_findings
    assert citations == sample_citations

    # Select outputs: PPT requires presentation_info
    next_tier = store.select_outputs(sid, ["ppt"])
    assert next_tier == InputTier.PRESENTATION_INFO

    record = store.get_session(sid)
    assert record["status"] == SessionStatus.COLLECTING_OUTPUTS.value
    assert record["output_types"] == [OutputType.PPT]
    assert record["selected_outputs"] == [OutputType.PPT]

    # Submit presentation_info
    ppt_data = {
        "problem_statement": "LLMs hallucinate without grounded context.",
        "tech_stack": ["Python", "LangChain", "ChromaDB"],
        "own_architecture_summary": "Vector retrieval pipeline with re-ranking.",
        "own_results_summary": "92% factuality score achieved.",
        "project_timeline": "Q1 2026",
    }
    res_ppt = store.submit_tier(sid, InputTier.PRESENTATION_INFO, ppt_data)
    assert res_ppt["ok"] is True
    assert res_ppt["error"] == ""
    assert res_ppt["next_tier"] is None
    assert res_ppt["is_complete"] is True

    record = store.get_session(sid)
    assert record["status"] == SessionStatus.READY.value
    assert isinstance(record["presentation_info"], ProjectPresentationInfo)

    # Retrieve bundle
    bundle = store.get_bundle(sid)
    assert bundle.cover_info.title == "RAG Architecture"
    assert bundle.project_presentation_info is not None
    assert bundle.project_presentation_info.problem_statement == (
        "LLMs hallucinate without grounded context."
    )
    assert bundle.academic_content_info is None


def test_zero_extra_tiers_literature_survey_straight_to_ready(sample_findings, sample_citations):
    """
    Test output selection requiring zero extra tiers (literature_survey only)
    going straight to ready status and returning next_tier as None.
    """
    store = SessionStore()
    sid = store.start_research("Quantum Computing")
    store.store_research_results(sid, sample_findings, sample_citations)

    # Literature survey needs only topic + output_types + cover_info, all pre-completed
    next_tier = store.select_outputs(sid, ["literature_survey"])
    assert next_tier is None

    record = store.get_session(sid)
    assert record["status"] == SessionStatus.READY.value
    assert record["output_types"] == [OutputType.LITERATURE_SURVEY]

    bundle = store.get_bundle(sid)
    assert bundle.cover_info.title == "Quantum Computing"
    assert bundle.project_presentation_info is None
    assert bundle.academic_content_info is None


def test_select_outputs_before_research_done_raises():
    """Calling select_outputs before research has completed must raise an error."""
    store = SessionStore()
    sid = store.start_research("AI Safety")

    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)research is not completed"):
        store.select_outputs(sid, ["literature_survey"])

    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)research is not completed"):
        store.select_outputs(sid, ["ppt"])


def test_get_bundle_before_outputs_selected_raises(sample_findings, sample_citations):
    """Calling get_bundle before outputs are selected must raise an error."""
    store = SessionStore()
    sid = store.start_research("AI Safety")

    # Before research is done
    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)research has not completed"):
        store.get_bundle(sid)

    # After research is done, but before outputs are selected
    store.store_research_results(sid, sample_findings, sample_citations)
    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)outputs have not been selected"):
        store.get_bundle(sid)


def test_get_research_results_before_research_done_raises():
    """Calling get_research_results before research is stored must raise an error."""
    store = SessionStore()
    sid = store.start_research("Robotics")

    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)not completed"):
        store.get_research_results(sid)


def test_store_research_results_state_machine_errors(sample_findings, sample_citations):
    """Calling store_research_results out of order must raise an error."""
    store = SessionStore()
    sid = store.start_research("Robotics")

    # Success first time
    store.store_research_results(sid, sample_findings, sample_citations)

    # Cannot call again once already past researching stage
    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)cannot store research results"):
        store.store_research_results(sid, sample_findings, sample_citations)

    # Cannot store with None
    sid2 = store.start_research("Robotics 2")
    with pytest.raises(ValueError, match="(?i)both findings and citations"):
        store.store_research_results(sid2, None, sample_citations)


def test_submit_tier_before_outputs_selected_raises(sample_findings, sample_citations):
    """Calling submit_tier before outputs are selected must raise an error."""
    store = SessionStore()
    sid = store.start_research("Robotics")

    # In researching state
    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)research has not completed"):
        store.submit_tier(sid, "cover_info", {"title": "Custom Title"})

    # In research_done state before select_outputs
    store.store_research_results(sid, sample_findings, sample_citations)
    with pytest.raises((ValueError, InvalidSessionStateError), match="(?i)outputs have not been selected"):
        store.submit_tier(sid, "cover_info", {"title": "Custom Title"})


def test_multi_tier_ppt_and_paper_flow(sample_findings, sample_citations):
    """Test flow with PPT and Research Paper outputs requiring multiple tiers."""
    store = SessionStore()
    sid = store.start_research("Retrieval Augmented Generation")
    store.store_research_results(sid, sample_findings, sample_citations)

    next_tier = store.select_outputs(sid, ["ppt", "research_paper"])
    assert next_tier == InputTier.PRESENTATION_INFO
    assert store.get_session(sid)["status"] == SessionStatus.COLLECTING_OUTPUTS.value

    # Incomplete bundle access raises
    with pytest.raises(ValueError, match="(?i)missing tiers.*presentation_info"):
        store.get_bundle(sid)

    # Submit presentation_info
    ppt_data = {
        "problem_statement": "LLMs hallucinate without grounded context.",
        "tech_stack": ["Python", "LangChain"],
        "own_architecture_summary": "RAG pipeline.",
        "own_results_summary": "92% factuality score.",
        "project_timeline": "Q1 2026",
    }
    res_ppt = store.submit_tier(sid, InputTier.PRESENTATION_INFO, ppt_data)
    assert res_ppt["ok"] is True
    assert res_ppt["next_tier"] == InputTier.ACADEMIC_INFO
    assert res_ppt["is_complete"] is False

    # Submit academic_info
    academic_data = {
        "methodology": "Benchmarked against standard QA datasets.",
        "dataset_or_sample": "HotpotQA",
        "tools_used": ["PyTorch"],
        "what_was_measured": "Exact Match and F1 score",
        "key_results": "F1 score increased by 18 points.",
        "limitations": "English only.",
    }
    res_academic = store.submit_tier(sid, "academic_info", academic_data)
    assert res_academic["ok"] is True
    assert res_academic["next_tier"] is None
    assert res_academic["is_complete"] is True

    record = store.get_session(sid)
    assert record["status"] == SessionStatus.READY.value

    bundle = store.get_bundle(sid)
    assert bundle.cover_info.title == "Retrieval Augmented Generation"
    assert bundle.project_presentation_info is not None
    assert bundle.academic_content_info is not None
    assert isinstance(bundle.academic_content_info, AcademicContentInfo)


def test_custom_cover_info_submission(sample_findings, sample_citations):
    """Users can submit custom cover_info to override the default title/metadata."""
    store = SessionStore()
    sid = store.start_research("Default Title")
    store.store_research_results(sid, sample_findings, sample_citations)
    store.select_outputs(sid, ["literature_survey"])

    cover_data = {
        "title": "Custom Survey Title",
        "authors": ["Dr. Smith", "Alice"],
        "institution": "MIT",
    }
    res = store.submit_tier(sid, "cover_info", cover_data)
    assert res["ok"] is True
    assert res["is_complete"] is True

    bundle = store.get_bundle(sid)
    assert bundle.cover_info.title == "Custom Survey Title"
    assert bundle.cover_info.authors == ["Dr. Smith", "Alice"]
    assert bundle.cover_info.institution == "MIT"


def test_invalid_tier_validation(sample_findings, sample_citations):
    """Validation errors must store nothing and return error information."""
    store = SessionStore()
    sid = store.start_research("Topic")
    store.store_research_results(sid, sample_findings, sample_citations)
    store.select_outputs(sid, ["ppt"])

    # Empty title for cover info
    invalid_cover = {"title": "   ", "authors": ["Alice"]}
    res = store.submit_tier(sid, "cover_info", invalid_cover)
    assert res["ok"] is False
    assert "title is required" in res["error"].lower()

    # Unknown tier
    res_unknown = store.submit_tier(sid, "unknown_tier", {"some": "data"})
    assert res_unknown["ok"] is False
    assert "Unknown input tier" in res_unknown["error"]


def test_unknown_session_errors():
    """Accessing or modifying an unknown session must raise SessionNotFoundError."""
    store = SessionStore()

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.get_session("non_existent_session_id")

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.store_research_results("non_existent_session_id", {}, {})

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.get_research_results("non_existent_session_id")

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.select_outputs("non_existent_session_id", ["literature_survey"])

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.submit_tier("non_existent_session_id", "cover_info", {"title": "Title"})

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.get_bundle("non_existent_session_id")


def test_invalid_inputs():
    """Invalid topic or output types must raise ValueError."""
    store = SessionStore()

    with pytest.raises(ValueError, match="(?i)research topic is required"):
        store.start_research("")

    with pytest.raises(ValueError, match="(?i)research topic is required"):
        store.start_research("   ")

    sid = store.start_research("Valid Topic")
    store.store_research_results(sid, {"dummy": 1}, {"dummy": 2})

    with pytest.raises(ValueError, match="(?i)at least one output type"):
        store.select_outputs(sid, [])

    with pytest.raises(ValueError, match="(?i)invalid output type"):
        store.select_outputs(sid, ["non_existent_output_type"])


def test_dict_interface_and_methods(sample_findings, sample_citations):
    """Test Mapping interface methods on SessionStore."""
    store = SessionStore()
    sid = store.start_research("Topic")
    store.store_research_results(sid, sample_findings, sample_citations)

    assert sid in store
    assert "fake_id" not in store
    assert len(store) == 1
    assert list(store) == [sid]

    record = store[sid]
    assert record["research_topic"] == "Topic"
    assert store.get(sid) is not None
    assert store.get("fake_id") is None

    store.update_status(sid, SessionStatus.COMPOSING)
    assert store[sid]["status"] == "composing"

    store.update_status(sid, SessionStatus.DONE)
    assert store[sid]["status"] == "done"

    store.update_status(sid, SessionStatus.ERROR)
    assert store[sid]["status"] == "error"

    with pytest.raises(ValueError, match="Invalid status"):
        store.update_status(sid, "invalid_status")

    store.clear()
    assert len(store) == 0


def test_module_level_convenience_functions(sample_findings, sample_citations):
    """Test module-level convenience functions using default session_store."""
    sid = start_research("Autonomous Agents")
    assert sid is not None

    record = get_session(sid)
    assert record["research_topic"] == "Autonomous Agents"

    store_research_results(sid, sample_findings, sample_citations)
    f, c = get_research_results(sid)
    assert f == sample_findings
    assert c == sample_citations

    next_tier = select_outputs(sid, ["literature_survey"])
    assert next_tier is None

    bundle = get_bundle(sid)
    assert bundle.cover_info.title == "Autonomous Agents"


def test_thread_safety_concurrency(sample_findings, sample_citations):
    """Test that concurrent operations with threading.RLock execute cleanly."""
    store = SessionStore()

    def worker(idx: int):
        topic = f"Topic {idx}"
        sid = store.start_research(topic)
        store.store_research_results(sid, sample_findings, sample_citations)
        f, c = store.get_research_results(sid)
        assert f == sample_findings

        next_tier = store.select_outputs(sid, ["ppt"])
        assert next_tier == InputTier.PRESENTATION_INFO

        ppt_data = {
            "problem_statement": f"Problem {idx}",
            "tech_stack": ["Python"],
            "own_architecture_summary": "Arch",
            "own_results_summary": "Results",
            "project_timeline": "2026",
        }
        res = store.submit_tier(sid, "presentation_info", ppt_data)
        assert res["ok"] is True
        assert res["is_complete"] is True

        bundle = store.get_bundle(sid)
        assert bundle.cover_info.title == topic
        assert bundle.project_presentation_info.problem_statement == f"Problem {idx}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        for f in futures:
            f.result()

    assert len(store) == 20
