"""
Tests for the FastAPI endpoints and WebSocket in backend/main.py.
All graph and external LLM/Search calls are replaced by fast fakes.
"""

from pathlib import Path
import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_or_create_tracker
from backend.orchestrator.session import SessionStatus, session_store, start_research
from backend.schemas.schemas import (
    CitationResult,
    Claim,
    ComposerResult,
    FindingsPacket,
    FormattedCitation,
    OutputType,
    PaperSummary,
    PipelineStatus,
    UserQAResponse,
)


@pytest.fixture(autouse=True)
def clean_session_store():
    """Ensure session store and trackers are reset for each test."""
    session_store.clear()
    from backend.main import _trackers
    _trackers.clear()
    yield
    session_store.clear()
    _trackers.clear()


@pytest.fixture
def sample_findings():
    return FindingsPacket(
        topic="FastAPI Architectures",
        summaries=[
            PaperSummary(
                paper_id="paper_1",
                summary="Study on high performance ASGI servers.",
                key_findings=["ASGI improves throughput by 4x."],
                extracted_claims=[
                    Claim(
                        claim_id="c1",
                        text="FastAPI handles async requests efficiently.",
                        source_paper_id="paper_1",
                        verification_status="verified",
                    )
                ],
            )
        ],
        claims=[
            Claim(
                claim_id="c1",
                text="FastAPI handles async requests efficiently.",
                source_paper_id="paper_1",
                verification_status="verified",
            )
        ],
        contradictions=[],
        cross_paper_synthesis="Synthesis text for FastAPI architectures.",
    )


@pytest.fixture
def sample_citations():
    return CitationResult(
        citation_style="apa",
        citations=[
            FormattedCitation(
                citation_id="cit1",
                paper_id="paper_1",
                citation_style="apa",
                inline_marker="(Tiangolo, 2020)",
                full_entry="Tiangolo, S. (2020). FastAPI Framework.",
            )
        ],
        bibliography=["Tiangolo, S. (2020). FastAPI Framework."],
    )


class FakeResearchGraph:
    def __init__(self, findings, citations, fail: bool = False, fail_detail: str = "Search failed"):
        self.findings = findings
        self.citations = citations
        self.fail = fail
        self.fail_detail = fail_detail

    def stream(self, state):
        yield {"search": {"search_results": None}}
        yield {"ingestion": {"ingestion_results": []}}
        if self.fail:
            yield {
                "search": {
                    "pipeline_status": PipelineStatus(stage="failed", detail=self.fail_detail)
                }
            }
            return
        yield {"summarization": {"findings": self.findings}}
        yield {"verification": {"verification_results": []}}
        yield {"citation": {"citations": self.citations}}


class FakeComposeGraph:
    def __init__(self, file_path_override: str | None = None):
        self.file_path_override = file_path_override

    def invoke(self, state):
        selected = state.get("selected_outputs") or [OutputType.PPT]
        results = []
        for item in selected:
            norm_ot = item if isinstance(item, OutputType) else OutputType(item)
            results.append(
                ComposerResult(
                    output_type=norm_ot,
                    title="Mock Document Title",
                    content="Mock Content",
                    sections={"Overview": "Overview section content"},
                    citations_used=["cit1"],
                    file_path=self.file_path_override,
                )
            )
        return {"composer_results": results}


def fake_user_qa(req):
    return UserQAResponse(
        answer=f"Answer for: {req.question}",
        source_paper_ids=["paper_1"],
    )


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------

def test_post_research_endpoint(sample_findings, sample_citations, monkeypatch):
    """POST /research returns session_id and starts background task."""
    fake_graph = FakeResearchGraph(sample_findings, sample_citations)
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        res = client.post("/research", json={"topic": "Quantum Computing"})
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

        # Invalid empty topic returns 400
        res_invalid = client.post("/research", json={"topic": "  "})
        assert res_invalid.status_code == 400


def test_websocket_research_streaming(sample_findings, sample_citations, monkeypatch):
    """WS /ws/research/{session_id} streams stage events and closes on research_done."""
    fake_graph = FakeResearchGraph(sample_findings, sample_citations)
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        # Create session
        res = client.post("/research", json={"topic": "Async Web Services"})
        sid = res.json()["session_id"]

        # Connect WebSocket
        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            stages_received = []
            while True:
                try:
                    data = ws.receive_json()
                    stages_received.append(data.get("stage"))
                    if data.get("stage") in ("research_done", "failed"):
                        break
                except Exception:
                    break

            assert "search" in stages_received
            assert "summarization" in stages_received
            assert "research_done" in stages_received


def test_websocket_research_failure_streaming(monkeypatch):
    """WS /ws/research/{session_id} pushes failed message when pipeline fails."""
    fake_graph = FakeResearchGraph(None, None, fail=True, fail_detail="No papers found for topic.")
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        res = client.post("/research", json={"topic": "Nonexistent Papers Topic"})
        sid = res.json()["session_id"]

        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            stages_received = []
            final_detail = None
            while True:
                try:
                    data = ws.receive_json()
                    stages_received.append(data.get("stage"))
                    if data.get("stage") == "failed":
                        final_detail = data.get("detail")
                        break
                except Exception:
                    break

            assert "failed" in stages_received
            assert "No papers found" in (final_detail or "")


def test_websocket_unknown_session():
    """WS /ws/research/{session_id} sends failure and closes on unknown session."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/research/unknown-uuid-123") as ws:
            data = ws.receive_json()
            assert data.get("stage") == "failed"
            assert "not found" in data.get("detail", "").lower()


def test_get_research_results_endpoint(sample_findings, sample_citations, monkeypatch):
    """GET /research/{session_id} returns 409 if not completed, 200 when done."""
    fake_graph = FakeResearchGraph(sample_findings, sample_citations)
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        # Unknown session -> 404
        res_404 = client.get("/research/unknown-uuid")
        assert res_404.status_code == 404

        # Start research
        res = client.post("/research", json={"topic": "Distributed Consensus"})
        sid = res.json()["session_id"]

        # Connect WebSocket to let background task stream to completion
        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            while True:
                data = ws.receive_json()
                if data.get("stage") in ("research_done", "failed"):
                    break

        # Now GET /research/{sid} should return 200 with findings
        res_findings = client.get(f"/research/{sid}")
        assert res_findings.status_code == 200
        data = res_findings.json()
        assert data["topic"] == "FastAPI Architectures"
        assert len(data["summaries"]) == 1
        assert data["summaries"][0]["paper_id"] == "paper_1"
        assert len(data["claims"]) == 1
        assert data["claims"][0]["verification_status"] == "verified"


def test_qa_endpoint(sample_findings, sample_citations, monkeypatch):
    """POST /research/{session_id}/qa runs question answering grounded in papers."""
    monkeypatch.setattr("backend.main.run_user_qa", fake_user_qa)
    fake_graph = FakeResearchGraph(sample_findings, sample_citations)
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        res = client.post("/research", json={"topic": "Vector Search"})
        sid = res.json()["session_id"]

        # Run QA
        res_qa = client.post(f"/research/{sid}/qa", json={"question": "How does vector search work?"})
        assert res_qa.status_code == 200
        qa_data = res_qa.json()
        assert "Answer for: How does vector search work?" in qa_data["answer"]
        assert qa_data["source_paper_ids"] == ["paper_1"]

        # Empty question -> 400
        res_empty = client.post(f"/research/{sid}/qa", json={"question": "   "})
        assert res_empty.status_code == 400

        # Unknown session -> 404
        res_unknown = client.post("/research/unknown-session/qa", json={"question": "Hello?"})
        assert res_unknown.status_code == 404


def test_output_selection_and_guided_input_endpoints(sample_findings, sample_citations, monkeypatch):
    """Test POST /outputs and POST /guided-input endpoints."""
    fake_graph = FakeResearchGraph(sample_findings, sample_citations)
    monkeypatch.setattr("backend.main.research_graph", fake_graph)

    with TestClient(app) as client:
        res = client.post("/research", json={"topic": "Neural Networks"})
        sid = res.json()["session_id"]

        # Calling outputs before research is done -> 409
        sid_pending = start_research("Pending Topic")
        res_early = client.post(f"/research/{sid_pending}/outputs", json={"output_types": ["ppt"]})
        assert res_early.status_code == 409

        # Complete research via WebSocket
        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            while True:
                data = ws.receive_json()
                if data.get("stage") == "research_done":
                    break

        # Select outputs: PPT requires presentation_info
        res_out = client.post(f"/research/{sid}/outputs", json={"output_types": ["ppt"]})
        assert res_out.status_code == 200
        assert res_out.json()["next_tier"] == "presentation_info"

        # Invalid output types -> 400
        res_bad = client.post(f"/research/{sid}/outputs", json={"output_types": ["invalid_type"]})
        assert res_bad.status_code == 400

        # Submit guided input tier
        ppt_payload = {
            "problem_statement": "Need scalable neural nets.",
            "tech_stack": ["PyTorch"],
            "own_architecture_summary": "Transformer based",
            "own_results_summary": "95% accuracy",
            "project_timeline": "2026",
        }
        res_tier = client.post(
            f"/research/{sid}/guided-input",
            json={"tier": "presentation_info", "value": ppt_payload},
        )
        assert res_tier.status_code == 200
        data_tier = res_tier.json()
        assert data_tier["ok"] is True
        assert data_tier["is_complete"] is True
        assert data_tier["next_tier"] is None


def test_compose_and_download_endpoints(tmp_path, sample_findings, sample_citations, monkeypatch):
    """Test POST /compose, GET /results, and GET /download/{session_id}/{output_type}."""
    # Create a real dummy file to stream via download
    mock_file = tmp_path / "ppt.pptx"
    mock_file.write_bytes(b"PK\x03\x04mock pptx binary content")

    fake_res_graph = FakeResearchGraph(sample_findings, sample_citations)
    fake_comp_graph = FakeComposeGraph(file_path_override=str(mock_file))
    monkeypatch.setattr("backend.main.research_graph", fake_res_graph)
    monkeypatch.setattr("backend.main.compose_graph", fake_comp_graph)

    with TestClient(app) as client:
        res = client.post("/research", json={"topic": "Transformers"})
        sid = res.json()["session_id"]

        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            while True:
                data = ws.receive_json()
                if data.get("stage") == "research_done":
                    break

        # Select PPT and submit tier
        client.post(f"/research/{sid}/outputs", json={"output_types": ["ppt"]})
        client.post(
            f"/research/{sid}/guided-input",
            json={
                "tier": "presentation_info",
                "value": {
                    "problem_statement": "Attention is all you need.",
                    "tech_stack": ["Python"],
                    "own_architecture_summary": "Transformer",
                    "own_results_summary": "SOTA",
                },
            },
        )

        # Trigger compose
        res_comp = client.post(f"/research/{sid}/compose")
        assert res_comp.status_code == 200
        assert res_comp.json()["status"] == "composing"

        # Wait briefly for synchronous fake compose worker to finish
        time.sleep(0.1)

        # GET /results
        res_results = client.get(f"/research/{sid}/results")
        assert res_results.status_code == 200
        results_list = res_results.json()
        assert len(results_list) == 1
        assert results_list[0]["output_type"] == "ppt"
        assert results_list[0]["download_url"] == f"/download/{sid}/ppt"

        # GET /download/{sid}/ppt
        res_download = client.get(f"/download/{sid}/ppt")
        assert res_download.status_code == 200
        assert b"mock pptx binary content" in res_download.content

        # GET unknown download -> 404
        res_down_404 = client.get(f"/download/{sid}/nonexistent")
        assert res_down_404.status_code == 404


def test_full_realistic_sequence_end_to_end(tmp_path, sample_findings, sample_citations, monkeypatch):
    """
    Test the full realistic flow end-to-end:
    POST /research -> WS /ws/research/{sid} -> GET /research/{sid} ->
    POST /qa -> POST /outputs -> POST /compose -> GET /results -> GET /download.
    """
    doc_file = tmp_path / "literature_survey.docx"
    doc_file.write_bytes(b"PK\x03\x04mock docx binary content")

    fake_res_graph = FakeResearchGraph(sample_findings, sample_citations)
    fake_comp_graph = FakeComposeGraph(file_path_override=str(doc_file))
    monkeypatch.setattr("backend.main.research_graph", fake_res_graph)
    monkeypatch.setattr("backend.main.compose_graph", fake_comp_graph)
    monkeypatch.setattr("backend.main.run_user_qa", fake_user_qa)

    with TestClient(app) as client:
        # 1. Start Research
        r1 = client.post("/research", json={"topic": "Quantum Machine Learning"})
        assert r1.status_code == 200
        sid = r1.json()["session_id"]

        # 2. Watch WebSocket progress to completion
        with client.websocket_connect(f"/ws/research/{sid}") as ws:
            received = []
            while True:
                msg = ws.receive_json()
                received.append(msg.get("stage"))
                if msg.get("stage") == "research_done":
                    break
            assert "research_done" in received

        # 3. View findings
        r2 = client.get(f"/research/{sid}")
        assert r2.status_code == 200
        assert r2.json()["topic"] == "FastAPI Architectures"

        # 4. Ask QA question
        r3 = client.post(f"/research/{sid}/qa", json={"question": "What is QML?"})
        assert r3.status_code == 200
        assert "Answer for: What is QML?" in r3.json()["answer"]

        # 5. Select output type (literature_survey goes straight to ready)
        r4 = client.post(f"/research/{sid}/outputs", json={"output_types": ["literature_survey"]})
        assert r4.status_code == 200
        assert r4.json()["next_tier"] is None

        # 6. Compose
        r5 = client.post(f"/research/{sid}/compose")
        assert r5.status_code == 200
        assert r5.json()["status"] == "composing"

        # Wait briefly for thread to finish
        time.sleep(0.1)

        # 7. Get download URLs
        r6 = client.get(f"/research/{sid}/results")
        assert r6.status_code == 200
        assert r6.json()[0]["output_type"] == "literature_survey"
        assert r6.json()[0]["download_url"] == f"/download/{sid}/literature_survey"

        # 8. Download document
        r7 = client.get(f"/download/{sid}/literature_survey")
        assert r7.status_code == 200
        assert r7.content == b"PK\x03\x04mock docx binary content"
