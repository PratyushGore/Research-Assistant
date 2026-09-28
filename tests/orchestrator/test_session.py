"""
Tests for the Orchestrator SessionStore.
"""

from concurrent.futures import ThreadPoolExecutor
import pytest

from backend.agents.guided_input.tiers import InputTier
from backend.orchestrator.session import (
    SessionNotFoundError,
    SessionStatus,
    SessionStore,
    create_session,
    get_bundle,
    get_session,
    submit_tier,
)
from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
)


def test_single_output_flow():
    """Test flow with a single output type (literature_survey)."""
    store = SessionStore()
    session_id, next_tier = store.create_session(
        topic="AI in Healthcare",
        output_types=["literature_survey"],
    )

    assert session_id is not None
    assert len(session_id) > 0
    assert next_tier == InputTier.COVER_INFO

    record = store.get_session(session_id)
    assert record["session_id"] == session_id
    assert record["research_topic"] == "AI in Healthcare"
    assert record["output_types"] == [OutputType.LITERATURE_SURVEY]
    assert record["status"] == SessionStatus.COLLECTING.value
    assert record["completed_tiers"] == ["topic", "output_types"]
    assert record["cover_info"] is None

    cover_data = {
        "title": "AI in Healthcare Survey",
        "authors": ["Dr. Smith"],
        "institution": "University Hospital",
    }
    result = store.submit_tier(session_id, "cover_info", cover_data)

    assert result["ok"] is True
    assert result["error"] == ""
    assert result["next_tier"] is None
    assert result["is_complete"] is True

    record = store.get_session(session_id)
    assert record["status"] == SessionStatus.READY.value
    assert "cover_info" in record["completed_tiers"]
    assert isinstance(record["cover_info"], CoverInfo)
    assert record["cover_info"].title == "AI in Healthcare Survey"

    # Bundle retrieval
    bundle = store.get_bundle(session_id)
    assert bundle.cover_info.title == "AI in Healthcare Survey"
    assert bundle.project_presentation_info is None
    assert bundle.academic_content_info is None


def test_ppt_plus_research_paper_flow():
    """Test flow with PPT and Research Paper outputs requiring multiple tiers."""
    store = SessionStore()
    session_id, next_tier = store.create_session(
        topic="RAG",
        output_types=["ppt", "research_paper"],
    )

    assert next_tier == InputTier.COVER_INFO

    # 1. Submit cover_info
    cover_data = {
        "title": "Retrieval Augmented Generation",
        "authors": ["Alice", "Bob"],
        "institution": "AI Lab",
    }
    res_cover = store.submit_tier(session_id, "cover_info", cover_data)
    assert res_cover["ok"] is True
    assert res_cover["error"] == ""
    assert res_cover["next_tier"] == InputTier.PRESENTATION_INFO
    assert res_cover["is_complete"] is False

    record = store.get_session(session_id)
    assert record["status"] == SessionStatus.COLLECTING.value

    # 2. Submit presentation_info
    ppt_data = {
        "problem_statement": "LLMs hallucinate without grounded context.",
        "tech_stack": ["Python", "LangChain", "ChromaDB"],
        "own_architecture_summary": "Vector retrieval pipeline with re-ranking.",
        "own_results_summary": "92% factuality score achieved.",
        "project_timeline": "Q1 2026",
    }
    res_ppt = store.submit_tier(session_id, InputTier.PRESENTATION_INFO, ppt_data)
    assert res_ppt["ok"] is True
    assert res_ppt["error"] == ""
    assert res_ppt["next_tier"] == InputTier.ACADEMIC_INFO
    assert res_ppt["is_complete"] is False

    # 3. Submit academic_info
    academic_data = {
        "methodology": "Benchmarked against standard QA datasets.",
        "dataset_or_sample": "HotpotQA and NaturalQuestions",
        "tools_used": ["Python", "PyTorch"],
        "what_was_measured": "Exact Match and F1 score",
        "key_results": "F1 score increased by 18 points.",
        "limitations": "Evaluated on English only.",
    }
    res_academic = store.submit_tier(session_id, "academic_info", academic_data)
    assert res_academic["ok"] is True
    assert res_academic["error"] == ""
    assert res_academic["next_tier"] is None
    assert res_academic["is_complete"] is True

    record = store.get_session(session_id)
    assert record["status"] == SessionStatus.READY.value

    # 4. Get bundle
    bundle = store.get_bundle(session_id)
    assert bundle.cover_info.title == "Retrieval Augmented Generation"
    assert bundle.project_presentation_info is not None
    assert bundle.project_presentation_info.problem_statement == (
        "LLMs hallucinate without grounded context."
    )
    assert bundle.academic_content_info is not None
    assert bundle.academic_content_info.methodology == (
        "Benchmarked against standard QA datasets."
    )


def test_invalid_tier_data():
    """Test validation errors: stores nothing and returns clear error."""
    store = SessionStore()
    session_id, next_tier = store.create_session(
        topic="Valid Topic",
        output_types=["ppt"],
    )
    assert next_tier == InputTier.COVER_INFO

    # Submit invalid cover info (empty title)
    invalid_cover = {"title": "   ", "authors": ["Alice"]}
    res = store.submit_tier(session_id, "cover_info", invalid_cover)

    assert res["ok"] is False
    assert "Project or paper title is required" in res["error"]
    assert res["next_tier"] == InputTier.COVER_INFO
    assert res["is_complete"] is False

    # Verify nothing was stored in the session record
    record = store.get_session(session_id)
    assert record["cover_info"] is None
    assert "cover_info" not in record["completed_tiers"]
    assert record["status"] == SessionStatus.COLLECTING.value

    # Submit unknown input tier
    res_unknown = store.submit_tier(session_id, "unknown_tier", {"some": "data"})
    assert res_unknown["ok"] is False
    assert "Unknown input tier" in res_unknown["error"]
    assert res_unknown["next_tier"] == InputTier.COVER_INFO
    assert res_unknown["is_complete"] is False

    # Submit non-dict/invalid structure
    res_malformed = store.submit_tier(session_id, "cover_info", 12345)
    assert res_malformed["ok"] is False
    assert "Cover information is required" in res_malformed["error"]


def test_duplicate_submission():
    """Submitting a tier twice must not create duplicates or re-request it."""
    store = SessionStore()
    session_id, _ = store.create_session(
        topic="RAG",
        output_types=["literature_survey"],
    )

    # First submission
    cover_1 = {"title": "Title Version 1"}
    res1 = store.submit_tier(session_id, "cover_info", cover_1)
    assert res1["ok"] is True
    assert res1["next_tier"] is None
    assert res1["is_complete"] is True

    record = store.get_session(session_id)
    assert record["completed_tiers"].count("cover_info") == 1
    assert record["cover_info"].title == "Title Version 1"

    # Second submission (update/duplicate)
    cover_2 = {"title": "Title Version 2"}
    res2 = store.submit_tier(session_id, "cover_info", cover_2)
    assert res2["ok"] is True
    assert res2["next_tier"] is None  # Not re-requested
    assert res2["is_complete"] is True

    record2 = store.get_session(session_id)
    assert record2["completed_tiers"].count("cover_info") == 1
    assert record2["cover_info"].title == "Title Version 2"

    # Test with multi-tier (PPT): duplicate cover_info doesn't reset or re-request
    session_id_ppt, _ = store.create_session("Topic PPT", ["ppt"])
    store.submit_tier(session_id_ppt, "cover_info", {"title": "V1"})
    res_dup = store.submit_tier(session_id_ppt, "cover_info", {"title": "V2"})
    assert res_dup["next_tier"] == InputTier.PRESENTATION_INFO  # Still presentation_info!
    assert store.get_session(session_id_ppt)["completed_tiers"].count("cover_info") == 1


def test_unknown_session():
    """Accessing or modifying an unknown session must raise a clear error."""
    store = SessionStore()

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.get_session("non_existent_session_id")

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.get_bundle("non_existent_session_id")

    with pytest.raises((KeyError, SessionNotFoundError), match="(?i)unknown session"):
        store.submit_tier("non_existent_session_id", "cover_info", {"title": "Title"})

    with pytest.raises(KeyError, match="(?i)unknown session"):
        _ = store["non_existent_session_id"]


def test_get_bundle_on_incomplete_session():
    """get_bundle must raise a clear error if the session is incomplete."""
    store = SessionStore()
    session_id, _ = store.create_session("Quantum Computing", ["literature_survey"])

    # Cover info not yet submitted
    with pytest.raises(ValueError, match="(?i)cover"):
        store.get_bundle(session_id)

    # Multi-tier session with only cover_info submitted
    session_id_ppt, _ = store.create_session("Quantum Computing", ["ppt"])
    store.submit_tier(
        session_id_ppt,
        "cover_info",
        {"title": "Quantum Computing Slides"},
    )
    with pytest.raises(ValueError, match="(?i)missing tiers.*presentation_info"):
        store.get_bundle(session_id_ppt)


def test_invalid_session_creation():
    """create_session with invalid topic or output_types must raise ValueError."""
    store = SessionStore()

    with pytest.raises(ValueError, match="(?i)research topic is required"):
        store.create_session("", ["literature_survey"])

    with pytest.raises(ValueError, match="(?i)at least one output type"):
        store.create_session("Topic", [])

    with pytest.raises(ValueError, match="(?i)invalid output type"):
        store.create_session("Topic", ["invalid_output_type"])


def test_dict_interface_and_methods():
    """Test Mapping interface methods on SessionStore."""
    store = SessionStore()
    session_id, _ = store.create_session("Topic", ["literature_survey"])

    assert session_id in store
    assert "fake_id" not in store
    assert len(store) == 1
    assert list(store) == [session_id]

    record = store[session_id]
    assert record["research_topic"] == "Topic"

    assert store.get(session_id) is not None
    assert store.get("fake_id") is None

    store.update_status(session_id, SessionStatus.RUNNING)
    assert store[session_id]["status"] == "running"

    with pytest.raises(ValueError, match="Invalid status"):
        store.update_status(session_id, "invalid_status")

    store.clear()
    assert len(store) == 0


def test_module_level_functions():
    """Test module-level convenience functions using default session_store."""
    session_id, next_tier = create_session("Autonomous Agents", ["literature_survey"])
    assert next_tier == InputTier.COVER_INFO

    record = get_session(session_id)
    assert record["research_topic"] == "Autonomous Agents"

    res = submit_tier(session_id, "cover_info", {"title": "Autonomous Agents"})
    assert res["ok"] is True
    assert res["is_complete"] is True

    bundle = get_bundle(session_id)
    assert bundle.cover_info.title == "Autonomous Agents"


def test_thread_safety_concurrency():
    """Test that concurrent operations with threading.Lock/RLock execute cleanly."""
    store = SessionStore()

    def worker(idx: int):
        sid, _ = store.create_session(f"Topic {idx}", ["literature_survey"])
        res = store.submit_tier(sid, "cover_info", {"title": f"Title {idx}"})
        assert res["ok"] is True
        bundle = store.get_bundle(sid)
        assert bundle.cover_info.title == f"Title {idx}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        for f in futures:
            f.result()

    assert len(store) == 20
