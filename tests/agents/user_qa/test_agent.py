"""
Tests for the User Q&A Agent.

Covers the four mandatory cases:
1. Normal answer generation grounded in retrieved chunks.
2. Empty retrieval resulting in a "not enough information" answer without calling LLM.
3. The allowed_paper_ids filter dropping chunks outside the set.
4. LLM failure handling returning a clear error answer without crashing.
"""
import hashlib
from unittest.mock import MagicMock, patch
from typing import Any, Optional

from backend.agents.user_qa.agent import (
    NOT_ENOUGH_INFO_ANSWER,
    UserQAAgent,
    _make_qa_cache_key,
    run_user_qa,
)
from backend.schemas.schemas import UserQARequest, UserQAResponse


class FakeGeminiClient:
    """Fake GeminiClient that tracks calls and supports simulated failures."""

    def __init__(
        self,
        response_text: str = "Test grounded answer.",
        should_fail: bool = False,
    ):
        self.response_text = response_text
        self.should_fail = should_fail
        self.call_history: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        *,
        paper_id: str,
        agent_name: str,
        purpose: str,
        use_cache: bool = True,
    ) -> str:
        self.call_history.append({
            "prompt": prompt,
            "paper_id": paper_id,
            "agent_name": agent_name,
            "purpose": purpose,
            "use_cache": use_cache,
        })
        if self.should_fail:
            raise RuntimeError("Gemini API rate limit exceeded (simulated).")
        return self.response_text


def sample_retrieval_results():
    """
    Simulates ChromaDB search_similar_chunks returning 3 chunks:
    2 chunks from p3, 1 chunk from p1.
    """
    return {
        "ids": [["c1", "c2", "c3"]],
        "documents": [[
            "Paper p3 evaluated a sample size of 500 patient records across three hospitals.",
            "Paper p3 demonstrated high statistical power with its 500 patient cohort.",
            "Paper p1 evaluated a smaller sample size of 50 subjects in a pilot study.",
        ]],
        "metadatas": [[
            {"paper_id": "p3", "page_number": 3, "section_heading": "Methods"},
            {"paper_id": "p3", "page_number": 4, "section_heading": "Discussion"},
            {"paper_id": "p1", "page_number": 2, "section_heading": "Cohort"},
        ]],
        "distances": [[0.12, 0.15, 0.28]],
    }


# ===========================================================================
# Case 1: Normal answer
# ===========================================================================
def test_user_qa_normal_answer():
    """Test standard Q&A flow with grounded response and deduplicated paper IDs."""
    request = UserQARequest(
        question="What sample size did paper p3 use?",
        topic="Clinical AI",
    )
    client = FakeGeminiClient(
        response_text="Paper p3 used a sample size of 500 patient records."
    )

    response = run_user_qa(
        request=request,
        client=client,
        search_fn=lambda q, top_k=5: sample_retrieval_results(),
    )

    assert isinstance(response, UserQAResponse)
    assert response.answer == "Paper p3 used a sample size of 500 patient records."
    # 2 chunks from p3 and 1 from p1 -> deduplicated to ["p3", "p1"] in order of appearance
    assert response.source_paper_ids == ["p3", "p1"]

    # Verify GeminiClient was called with proper token/cache arguments
    assert len(client.call_history) == 1
    call = client.call_history[0]
    expected_cache_key = f"qa_{hashlib.sha256(request.question.strip().lower().encode('utf-8')).hexdigest()[:16]}"
    assert call["paper_id"] == expected_cache_key
    assert call["paper_id"] == _make_qa_cache_key(request.question)
    assert call["agent_name"] == "user_qa_agent"
    assert call["purpose"] == "user_qa_answer"
    assert call["use_cache"] is True
    assert "What sample size did paper p3 use?" in call["prompt"]
    assert "Paper p3 evaluated a sample size of 500" in call["prompt"]


# ===========================================================================
# Case 2: Empty retrieval
# ===========================================================================
def test_user_qa_empty_retrieval():
    """If retrieval returns nothing usable, return not-enough-info without calling LLM."""
    request = UserQARequest(
        question="What were the hyperparameter settings for model XYZ?",
        topic="Deep Learning",
    )
    client = FakeGeminiClient()

    # ChromaDB returning empty 2D lists
    empty_results = {"documents": [[]], "metadatas": [[]], "ids": [[]]}
    response = run_user_qa(
        request=request,
        client=client,
        search_fn=lambda q, top_k=5: empty_results,
    )

    assert "not contain enough information" in response.answer.lower()
    assert response.source_paper_ids == []
    # Gemini must NOT be called
    assert len(client.call_history) == 0

    # Also test empty list [] return (e.g. from empty query)
    response_list = run_user_qa(
        request=request,
        client=client,
        search_fn=lambda q, top_k=5: [],
    )
    assert "not contain enough information" in response_list.answer.lower()
    assert response_list.source_paper_ids == []
    assert len(client.call_history) == 0


# ===========================================================================
# Case 3: The allowed_paper_ids filter
# ===========================================================================
def test_user_qa_allowed_paper_ids_filter():
    """Chunks whose paper_id is not in allowed_paper_ids must be dropped."""
    request = UserQARequest(
        question="What sample size did paper p3 use?",
        topic="Clinical AI",
    )
    client = FakeGeminiClient(
        response_text="Paper p3 used a sample size of 500 patient records."
    )

    # Filter to only allow p3 (p1 chunk must be dropped)
    response = run_user_qa(
        request=request,
        allowed_paper_ids={"p3"},
        client=client,
        search_fn=lambda q, top_k=5: sample_retrieval_results(),
    )

    assert response.source_paper_ids == ["p3"]
    assert len(client.call_history) == 1
    # Verify p1 text was excluded from the prompt
    prompt = client.call_history[0]["prompt"]
    assert "Paper p1 evaluated a smaller sample size" not in prompt
    assert "Paper p3 evaluated a sample size of 500" in prompt


def test_user_qa_allowed_paper_ids_drops_all_chunks():
    """If allowed_paper_ids filters out all retrieved chunks, do not call Gemini."""
    request = UserQARequest(
        question="What sample size did paper p3 use?",
        topic="Clinical AI",
    )
    client = FakeGeminiClient()

    # Allowed paper is p99, but retrieval only has p3 and p1
    response = run_user_qa(
        request=request,
        allowed_paper_ids={"p99"},
        client=client,
        search_fn=lambda q, top_k=5: sample_retrieval_results(),
    )

    assert "not contain enough information" in response.answer.lower()
    assert response.source_paper_ids == []
    # LLM must not be called
    assert len(client.call_history) == 0


# ===========================================================================
# Case 4: LLM failure
# ===========================================================================
def test_user_qa_llm_failure():
    """If Gemini raises an exception, return a clear error answer and never crash."""
    request = UserQARequest(
        question="What sample size did paper p3 use?",
        topic="Clinical AI",
    )
    client = FakeGeminiClient(should_fail=True)

    response = run_user_qa(
        request=request,
        client=client,
        search_fn=lambda q, top_k=5: sample_retrieval_results(),
    )

    assert isinstance(response, UserQAResponse)
    assert response.answer.startswith("Error generating answer:")
    assert "rate limit exceeded" in response.answer
    assert response.source_paper_ids == []


# ===========================================================================
# Additional tests: Mocking default store function & Token discipline
# ===========================================================================
def test_user_qa_with_mocked_store():
    """Verify that run_user_qa calls search_similar_chunks by default when no search_fn is given."""
    request = UserQARequest(
        question="What sample size did paper p3 use?",
        topic="Clinical AI",
    )
    client = FakeGeminiClient(response_text="Sample size was 500.")

    with patch(
        "backend.agents.user_qa.agent.search_similar_chunks",
        return_value=sample_retrieval_results(),
    ) as mock_search:
        response = run_user_qa(
            request=request,
            client=client,
            top_k=3,
        )

        mock_search.assert_called_once_with(
            "What sample size did paper p3 use?",
            top_k=3,
        )
        assert response.answer == "Sample size was 500."
        assert response.source_paper_ids == ["p3", "p1"]


def test_user_qa_agent_class():
    """Verify UserQAAgent class methods directly."""
    agent = UserQAAgent(client=FakeGeminiClient(response_text="Direct agent answer."))
    request = UserQARequest(question="Test question?", topic="General")

    resp = agent.answer_question(
        request=request,
        search_fn=lambda q, top_k=5: sample_retrieval_results(),
    )
    assert resp.answer == "Direct agent answer."
    assert resp.source_paper_ids == ["p3", "p1"]


def test_user_qa_retrieval_exception_handling():
    """If the vector store search raises an exception, handle gracefully without crashing."""
    request = UserQARequest(question="What is the result?", topic="Testing")

    def broken_search(q, top_k=5):
        raise ConnectionError("Vector store unavailable")

    resp = run_user_qa(
        request=request,
        client=FakeGeminiClient(),
        search_fn=broken_search,
    )

    assert resp.answer.startswith("Error retrieving relevant research papers:")
    assert resp.source_paper_ids == []


def test_user_qa_caching_with_special_characters(tmp_path, monkeypatch):
    """
    Test that questions containing ?, :, and / safely write to disk cache in tmp_path
    and a second identical call returns the cached answer without calling the client again.
    """
    import backend.agents.common.llm_client as llm_module
    from backend.agents.common.llm_client import GeminiClient

    # Point LLM CACHE_DIR to the pytest temp directory
    monkeypatch.setattr(llm_module, "CACHE_DIR", tmp_path)

    question_with_special_chars = (
        "What is the accuracy of model:v1 on 2024/2025 benchmarks? Does it scale?"
    )
    request = UserQARequest(
        question=question_with_special_chars,
        topic="Model Benchmark Evaluation",
    )

    # Use a real GeminiClient instance with mocked model generator
    client = GeminiClient(api_key="mock-key-for-test")
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "The accuracy of model:v1 is 96.5%."
    client._ensure_model = MagicMock(return_value=mock_model)

    search_fn = lambda q, top_k=5: sample_retrieval_results()

    # First call: Cache miss -> invokes client and performs real write to tmp_path
    resp1 = run_user_qa(request=request, client=client, search_fn=search_fn)
    assert resp1.answer == "The accuracy of model:v1 is 96.5%."
    assert resp1.source_paper_ids == ["p3", "p1"]
    assert mock_model.generate_content.call_count == 1

    # Confirm cache file was actually written to tmp_path on disk
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    expected_hash = hashlib.sha256(
        question_with_special_chars.strip().lower().encode("utf-8")
    ).hexdigest()[:16]
    expected_cache_prefix = f"qa_{expected_hash}"
    assert cache_files[0].name.startswith(expected_cache_prefix)

    # Second identical call: Cache hit -> reads from disk without calling client again
    resp2 = run_user_qa(request=request, client=client, search_fn=search_fn)
    assert resp2.answer == "The accuracy of model:v1 is 96.5%."
    assert resp2.source_paper_ids == ["p3", "p1"]
    # Model should NOT have been called a second time
    assert mock_model.generate_content.call_count == 1

