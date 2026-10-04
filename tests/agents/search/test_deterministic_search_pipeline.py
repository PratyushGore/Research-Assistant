import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from backend.agents.search.agent import (
    search_papers,
    search_papers_pool,
)
from backend.main import app
from backend.orchestrator.graph import (
    ingestion_agent,
    research_graph,
    search_agent,
    summarization_agent,
)
from backend.orchestrator.session import get_session
from backend.schemas.schemas import (
    Chunk,
    Claim,
    FindingsPacket,
    IngestionResult,
    PaperMetadata,
    PaperSummary,
    SearchResult,
    VerificationResult,
)


def _make_candidate(index: int) -> PaperMetadata:
    return PaperMetadata(
        paper_id=f"arxiv:paper_{index:03d}",
        title=f"Sample Research Paper {index}",
        authors=[f"Author {index}"],
        year=2024,
        url=f"https://arxiv.org/abs/2401.{index:04d}",
        venue="arXiv",
    )


# ---------------------------------------------------------------------------
# Part E Tests
# ---------------------------------------------------------------------------

def test_20_candidates_request_8_deterministic_order(tmp_path):
    """
    20 candidates + request 8 -> exactly 8 ingested, identical ids on a second run.
    """
    candidates = [_make_candidate(i) for i in range(20)]
    mock_search_result = SearchResult(query="topic test", papers=candidates, total_results=20)

    def mock_ingest(url, metadata):
        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[Chunk(chunk_id=f"{metadata.paper_id}:c1", paper_id=metadata.paper_id, text="text")],
            raw_text="Sample text",
        )

    with patch("backend.agents.search.agent.search_papers_pool", return_value=mock_search_result), \
         patch("backend.agents.ingestion.agent.ingest_and_store_pdf", side_effect=mock_ingest):

        state_1 = {"research_topic": "topic test", "max_papers": 8}
        s1 = search_agent(state_1)
        res1 = ingestion_agent(s1)

        state_2 = {"research_topic": "topic test", "max_papers": 8}
        s2 = search_agent(state_2)
        res2 = ingestion_agent(s2)

    assert len(res1["ingestion_results"]) == 8
    assert len(res2["ingestion_results"]) == 8

    ids_1 = [ir.paper_id for ir in res1["ingestion_results"]]
    ids_2 = [ir.paper_id for ir in res2["ingestion_results"]]

    assert ids_1 == ids_2 == [f"arxiv:paper_{i:03d}" for i in range(8)]
    assert res1["available_papers"] == 8
    assert res1["requested_papers"] == 8
    assert res1["paper_notice"] is None


def test_semantic_scholar_failing_does_not_change_8(tmp_path, monkeypatch):
    """
    Semantic Scholar failing does not change the first 8 papers.
    """
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path))
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
    """ + "".join(f"""
      <entry>
        <id>http://arxiv.org/abs/2101.{i:04d}v1</id>
        <title>ArXiv Paper {i}</title>
        <summary>Summary {i}</summary>
        <published>2021-01-01</published>
        <author><name>Author {i}</name></author>
      </entry>
    """ for i in range(25)) + "</feed>"

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.text = sample_xml
    mock_resp.raise_for_status = Mock()

    # Case 1: Semantic Scholar succeeds or is not needed
    with patch("backend.agents.search.agent.requests.get", return_value=mock_resp), \
         patch("backend.agents.search.agent.time.sleep", return_value=None):
        pool1 = search_papers_pool("topic a", target=8)

    # Clear cache to simulate fresh run with Semantic Scholar failing
    for f in tmp_path.glob("*.json"):
        f.unlink()

    # Case 2: Semantic Scholar raises Exception
    with patch("backend.agents.search.agent.requests.get", return_value=mock_resp), \
         patch("backend.agents.search.agent.search_semantic_scholar", side_effect=Exception("S2 down")), \
         patch("backend.agents.search.agent.time.sleep", return_value=None):
        pool2 = search_papers_pool("topic a", target=8)

    ids1 = [p.paper_id for p in pool1.papers[:8]]
    ids2 = [p.paper_id for p in pool2.papers[:8]]
    assert len(ids1) == 8
    assert ids1 == ids2


def test_cache_hit_makes_zero_network_calls(tmp_path, monkeypatch):
    """
    A cache hit makes zero network calls when holding enough candidates.
    """
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path))
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
    """ + "".join(f"""
      <entry>
        <id>http://arxiv.org/abs/2202.{i:04d}v1</id>
        <title>Cached Paper {i}</title>
        <summary>Summary {i}</summary>
        <published>2022-02-01</published>
        <author><name>Author {i}</name></author>
      </entry>
    """ for i in range(25)) + "</feed>"

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.text = sample_xml
    mock_resp.raise_for_status = Mock()

    # First call: populates cache
    with patch("backend.agents.search.agent.requests.get", return_value=mock_resp) as mock_get, \
         patch("backend.agents.search.agent.time.sleep", return_value=None):
        res1 = search_papers_pool("caching topic", target=8)
        assert mock_get.call_count >= 1

    # Second call: must hit cache with 0 network calls
    with patch("backend.agents.search.agent.requests.get") as mock_get_2:
        res2 = search_papers_pool("caching topic", target=8)
        assert mock_get_2.call_count == 0

    assert len(res1.papers) == len(res2.papers) == 20
    assert [p.paper_id for p in res1.papers] == [p.paper_id for p in res2.papers]


def test_request_15_with_only_9_candidates_notice():
    """
    Request 15 with only 9 candidates -> 9 papers + the notice text:
    'You asked for 15 papers but only 9 were available for this topic.'
    """
    candidates = [_make_candidate(i) for i in range(9)]
    mock_search_result = SearchResult(query="rare topic", papers=candidates, total_results=9)

    def mock_ingest(url, metadata):
        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[Chunk(chunk_id=f"{metadata.paper_id}:c1", paper_id=metadata.paper_id, text="text")],
            raw_text="Sample text",
        )

    with patch("backend.agents.search.agent.search_papers_pool", return_value=mock_search_result), \
         patch("backend.agents.ingestion.agent.ingest_and_store_pdf", side_effect=mock_ingest):

        state = {"research_topic": "rare topic", "max_papers": 15}
        s_state = search_agent(state)
        i_state = ingestion_agent(s_state)

    assert len(i_state["ingestion_results"]) == 9
    assert i_state["requested_papers"] == 15
    assert i_state["available_papers"] == 9
    assert (
        i_state["paper_notice"]
        == "You asked for 15 papers but only 9 were available for this topic."
    )

    # Verify summarization agent propagates notice and counts to findings
    mock_findings = FindingsPacket(
        topic="rare topic",
        summaries=[PaperSummary(paper_id=f"arxiv:paper_{i:03d}", summary=f"Summary {i}") for i in range(9)],
        claims=[],
    )
    with patch("backend.agents.summarization.agent.run_summarization", return_value=mock_findings):
        sum_state = summarization_agent(i_state)

    findings = sum_state["findings"]
    assert findings.requested_papers == 15
    assert findings.available_papers == 9
    assert (
        findings.paper_notice
        == "You asked for 15 papers but only 9 were available for this topic."
    )
    assert len(findings.summaries) == 9


def test_3_pdf_failures_fall_through_to_later_candidates():
    """
    3 PDF failures fall through to later candidates until target is reached.
    """
    candidates = [_make_candidate(i) for i in range(20)]
    mock_search_result = SearchResult(query="fault tolerant", papers=candidates, total_results=20)

    # First 3 candidates fail PDF download on all attempts
    def mock_ingest(url, metadata):
        if metadata.paper_id in ("arxiv:paper_000", "arxiv:paper_001", "arxiv:paper_002"):
            raise Exception("PDF download failed 404")
        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[Chunk(chunk_id=f"{metadata.paper_id}:c1", paper_id=metadata.paper_id, text="text")],
            raw_text="Sample text",
        )

    with patch("backend.agents.search.agent.search_papers_pool", return_value=mock_search_result), \
         patch("backend.agents.ingestion.agent.ingest_and_store_pdf", side_effect=mock_ingest):

        state = {"research_topic": "fault tolerant", "max_papers": 8}
        s_state = search_agent(state)
        i_state = ingestion_agent(s_state)

    assert len(i_state["ingestion_results"]) == 8
    ingested_ids = [ir.paper_id for ir in i_state["ingestion_results"]]
    # Should skip 0, 1, 2 and ingest 3 through 10
    expected_ids = [f"arxiv:paper_{i:03d}" for i in range(3, 11)]
    assert ingested_ids == expected_ids
    assert i_state["available_papers"] == 8
    assert i_state["requested_papers"] == 8
    assert i_state["paper_notice"] is None


def test_arxiv_429_triggers_backoff_then_success(tmp_path, monkeypatch):
    """
    arXiv 429 triggers backoff then success.
    """
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path))
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2301.0001v1</id>
        <title>Retry Success Paper</title>
        <summary>Summary</summary>
        <published>2023-01-01</published>
        <author><name>Author A</name></author>
      </entry>
    </feed>
    """

    resp_429 = Mock()
    resp_429.status_code = 429

    resp_200 = Mock()
    resp_200.status_code = 200
    resp_200.text = sample_xml
    resp_200.raise_for_status = Mock()

    import backend.agents.search.agent as search_module
    search_module._last_arxiv_request_time = 0.0

    sleep_calls = []

    def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch("backend.agents.search.agent.requests.get", side_effect=[resp_429, resp_200]), \
         patch("backend.agents.search.agent.time.sleep", side_effect=mock_sleep):
        result = search_papers_pool("retry topic", target=3)

    assert len(sleep_calls) >= 1
    assert any(s >= 3.0 for s in sleep_calls)
    assert len(result.papers) == 1
    assert result.papers[0].title == "Retry Success Paper"


def test_validation_min_max_default_papers():
    """
    Validation (2 -> 422, 16 -> 422, default 8).
    """
    client = TestClient(app)

    # 2 is below minimum of 3 -> 422
    resp_below = client.post("/research", json={"topic": "Quantum", "max_papers": 2})
    assert resp_below.status_code == 422

    # 16 is above maximum of 15 -> 422
    resp_above = client.post("/research", json={"topic": "Quantum", "max_papers": 16})
    assert resp_above.status_code == 422

    # Default value is 8 when omitted
    with patch("backend.main._executor.submit", return_value=None):
        resp_default = client.post("/research", json={"topic": "Quantum"})
        assert resp_default.status_code == 200
        session_id = resp_default.json()["session_id"]
        session_record = get_session(session_id)
        assert session_record["max_papers"] == 8


def test_search_papers_old_behaviour_unchanged():
    """
    search_papers() old behaviour unchanged.
    """
    empty = search_papers("")
    assert empty.total_results == 0
    assert empty.papers == []

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2101.9999v1</id>
        <title>Legacy Test Paper</title>
        <summary>Summary</summary>
        <published>2021-01-01</published>
        <author><name>Author L</name></author>
      </entry>
    </feed>
    """
    mock_resp.raise_for_status = Mock()

    with patch("backend.agents.search.agent.requests.get", return_value=mock_resp), \
         patch("backend.agents.search.agent.search_semantic_scholar", return_value=[]), \
         patch("backend.agents.search.agent.search_core", return_value=[]):
        res = search_papers("legacy topic", max_results_per_source=1)

    assert res.total_results == 1
    assert res.papers[0].title == "Legacy Test Paper"


# ---------------------------------------------------------------------------
# Part F End-to-End Test
# ---------------------------------------------------------------------------

def test_end_to_end_request_10_with_40_candidates_available():
    """
    End-to-end test (mock network):
    request 10 with 40 candidates available -> exactly 10 papers appear in
    findings.summaries, in citations/references, and in findings.available_papers (== 10);
    no candidate beyond those 10 appears anywhere in the output.
    """
    candidates = [_make_candidate(i) for i in range(40)]
    mock_search_result = SearchResult(query="AI Ethics", papers=candidates, total_results=40)

    def mock_ingest(url, metadata):
        return IngestionResult(
            paper_id=metadata.paper_id,
            metadata=metadata,
            chunks=[Chunk(chunk_id=f"{metadata.paper_id}:chunk:1", paper_id=metadata.paper_id, text="Ethical AI content.")],
            raw_text="Ethical AI content.",
        )

    def mock_summarize(topic, ingestion_results, client=None):
        summaries = [
            PaperSummary(
                paper_id=ir.paper_id,
                summary=f"Summary for {ir.paper_id}",
                key_findings=["Key finding"],
                extracted_claims=[
                    Claim(
                        claim_id=f"{ir.paper_id}:claim:1",
                        text=f"Claim from {ir.paper_id}",
                        source_paper_id=ir.paper_id,
                        source_chunk_ids=[f"{ir.paper_id}:chunk:1"],
                    )
                ],
            )
            for ir in ingestion_results
        ]
        claims = [c for s in summaries for c in s.extracted_claims]
        return FindingsPacket(topic=topic, summaries=summaries, claims=claims)

    def mock_verify(findings, ingestion_results, **kwargs):
        results = [
            VerificationResult(
                claim_id=c.claim_id,
                verification_status="verified",
                confidence_score=1.0,
                explanation="Grounded",
                supporting_chunk_ids=c.source_chunk_ids,
            )
            for c in findings.claims
        ]
        return results, findings

    initial_state = {
        "request_id": "test_session_e2e_10",
        "research_topic": "AI Ethics",
        "max_papers": 10,
    }

    with patch("backend.agents.search.agent.search_papers_pool", return_value=mock_search_result), \
         patch("backend.agents.ingestion.agent.ingest_and_store_pdf", side_effect=mock_ingest), \
         patch("backend.agents.summarization.agent.run_summarization", side_effect=mock_summarize), \
         patch("backend.agents.verification.agent.run_verification", side_effect=mock_verify):

        final_state = research_graph.invoke(initial_state)

    findings = final_state.get("findings")
    citations = final_state.get("citations")

    assert findings is not None
    assert citations is not None

    # Exactly 10 papers appear in findings.summaries
    assert len(findings.summaries) == 10
    assert findings.available_papers == 10
    assert findings.requested_papers == 10
    assert findings.paper_notice is None

    first_10_ids = [f"arxiv:paper_{i:03d}" for i in range(10)]
    summary_ids = [s.paper_id for s in findings.summaries]
    assert summary_ids == first_10_ids

    # Exactly 10 citations and bibliography entries
    assert len(citations.citations) == 10
    assert len(citations.bibliography) == 10

    citation_paper_ids = [c.paper_id for c in citations.citations]
    assert citation_paper_ids == first_10_ids

    # Verify NO candidate beyond those 10 appears anywhere in the output
    beyond_ids = {f"arxiv:paper_{i:03d}" for i in range(10, 40)}
    all_summary_ids = {s.paper_id for s in findings.summaries}
    all_citation_ids = {c.paper_id for c in citations.citations}
    all_claim_source_ids = {c.source_paper_id for c in findings.claims}
    all_bib_text = " ".join(citations.bibliography)

    assert not (all_summary_ids & beyond_ids)
    assert not (all_citation_ids & beyond_ids)
    assert not (all_claim_source_ids & beyond_ids)
    for beyond_id in beyond_ids:
        assert beyond_id not in all_bib_text
