"""
FastAPI application for Multi-Agent AI Research & Publication Assistant.
Connects Orchestrator session layer, research_graph, compose_graph, and user_qa.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.agents.user_qa.agent import run_user_qa
from backend.orchestrator.graph import compose_graph, research_graph
from backend.orchestrator.session import (
    InvalidSessionStateError,
    SessionIncompleteError,
    SessionNotFoundError,
    SessionStatus,
    get_bundle,
    get_research_results,
    get_session,
    select_outputs,
    session_store,
    start_research,
    store_research_results,
    submit_tier,
)
from backend.schemas.schemas import ComposerResult, UserQARequest, UserQAResponse

logger = logging.getLogger("research_assistant.api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Multi-Agent AI Research & Publication Assistant API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    topic: str = Field(..., description="Research topic to investigate")


class QARequest(BaseModel):
    question: str = Field(..., description="Question grounded in ingested research papers")


class OutputSelectionRequest(BaseModel):
    output_types: list[str] = Field(..., description="List of desired output types")


class GuidedInputRequest(BaseModel):
    tier: str = Field(..., description="Tier name (e.g. cover_info, presentation_info)")
    value: dict[str, Any] = Field(..., description="Tier payload data")


# ---------------------------------------------------------------------------
# In-Memory Tracking for Background Tasks
# ---------------------------------------------------------------------------

class SessionTaskTracker:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.events: list[dict[str, Any]] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.is_done: bool = False
        self.failed: bool = False
        self.error_detail: Optional[str] = None
        self.composer_results: list[ComposerResult] = []
        self.composing: bool = False

    def broadcast_event(self, event: dict[str, Any], loop: asyncio.AbstractEventLoop) -> None:
        self.events.append(event)
        for queue in list(self.subscribers):
            loop.call_soon_threadsafe(queue.put_nowait, event)


_trackers: dict[str, SessionTaskTracker] = {}
_executor = ThreadPoolExecutor(max_workers=10)


def get_or_create_tracker(session_id: str) -> SessionTaskTracker:
    if session_id not in _trackers:
        _trackers[session_id] = SessionTaskTracker(session_id)
    return _trackers[session_id]


# ---------------------------------------------------------------------------
# Global Exception Handlers (Clean JSON errors, no raw tracebacks)
# ---------------------------------------------------------------------------

@app.exception_handler(SessionNotFoundError)
async def session_not_found_handler(request: Request, exc: SessionNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidSessionStateError)
async def invalid_session_state_handler(request: Request, exc: InvalidSessionStateError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(SessionIncompleteError)
async def session_incomplete_handler(request: Request, exc: SessionIncompleteError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


# ---------------------------------------------------------------------------
# Background Workers
# ---------------------------------------------------------------------------

def _run_research_sync(session_id: str, topic: str, loop: asyncio.AbstractEventLoop) -> None:
    tracker = get_or_create_tracker(session_id)
    initial_state = {
        "request_id": session_id,
        "research_topic": topic,
    }
    accumulated_state: dict[str, Any] = dict(initial_state)

    try:
        for chunk in research_graph.stream(initial_state):
            for node_name, node_output in chunk.items():
                if isinstance(node_output, dict):
                    accumulated_state.update(node_output)

                # Check for failure status in node output or accumulated state
                status_obj = None
                if isinstance(node_output, dict):
                    status_obj = node_output.get("pipeline_status")
                if status_obj is None:
                    status_obj = accumulated_state.get("pipeline_status")

                stage_failed = False
                fail_detail = None
                if status_obj is not None:
                    s_stage = getattr(status_obj, "stage", None)
                    if s_stage is None and isinstance(status_obj, dict):
                        s_stage = status_obj.get("stage")
                    if s_stage == "failed":
                        stage_failed = True
                        fail_detail = getattr(status_obj, "detail", None)
                        if fail_detail is None and isinstance(status_obj, dict):
                            fail_detail = status_obj.get("detail")

                if stage_failed:
                    detail = fail_detail or f"Failed during {node_name}"
                    event = {"stage": "failed", "detail": detail}
                    tracker.broadcast_event(event, loop)
                    session_store.update_status(session_id, SessionStatus.ERROR)
                    tracker.failed = True
                    tracker.error_detail = detail
                    tracker.is_done = True
                    return

                # Normal node progression event
                event = {"stage": node_name, "detail": f"{node_name.capitalize()} completed."}
                tracker.broadcast_event(event, loop)

        # Stream finished, check final accumulated findings & citations
        findings = accumulated_state.get("findings")
        citations = accumulated_state.get("citations")
        status_obj = accumulated_state.get("pipeline_status")

        if status_obj is not None:
            s_stage = getattr(status_obj, "stage", None)
            if s_stage is None and isinstance(status_obj, dict):
                s_stage = status_obj.get("stage")
            if s_stage == "failed":
                detail = (
                    getattr(status_obj, "detail", None)
                    or "Research pipeline failed."
                )
                event = {"stage": "failed", "detail": detail}
                tracker.broadcast_event(event, loop)
                session_store.update_status(session_id, SessionStatus.ERROR)
                tracker.failed = True
                tracker.error_detail = detail
                tracker.is_done = True
                return

        if findings is not None and citations is not None:
            store_research_results(session_id, findings, citations)
            event = {"stage": "research_done", "detail": "Research completed successfully."}
            tracker.broadcast_event(event, loop)
            tracker.is_done = True
        else:
            detail = "Research ended without producing complete findings and citations."
            event = {"stage": "failed", "detail": detail}
            tracker.broadcast_event(event, loop)
            session_store.update_status(session_id, SessionStatus.ERROR)
            tracker.failed = True
            tracker.error_detail = detail
            tracker.is_done = True

    except Exception as exc:
        logger.exception("Research task failed for session %s: %s", session_id, exc)
        try:
            session_store.update_status(session_id, SessionStatus.ERROR)
        except Exception:
            pass
        detail = str(exc)
        event = {"stage": "failed", "detail": detail}
        tracker.broadcast_event(event, loop)
        tracker.failed = True
        tracker.error_detail = detail
        tracker.is_done = True


def _run_compose_sync(session_id: str, compose_state: dict[str, Any]) -> None:
    tracker = get_or_create_tracker(session_id)
    try:
        final_state = compose_graph.invoke(compose_state)
        composer_results = final_state.get("composer_results", [])
        tracker.composer_results = composer_results

        record = get_session(session_id)
        record["composer_results"] = composer_results
        session_store.update_status(session_id, SessionStatus.DONE)
        tracker.composing = False
    except Exception as exc:
        logger.exception("Compose task failed for session %s: %s", session_id, exc)
        session_store.update_status(session_id, SessionStatus.ERROR)
        tracker.composing = False
        tracker.failed = True
        tracker.error_detail = str(exc)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/research", status_code=status.HTTP_200_OK)
async def create_research(body: ResearchRequest):
    """
    Start research from a topic and launch background research graph execution.
    """
    if not body.topic or not body.topic.strip():
        raise HTTPException(status_code=400, detail="Research topic cannot be empty.")

    topic = body.topic.strip()
    session_id = start_research(topic)
    tracker = get_or_create_tracker(session_id)

    loop = asyncio.get_running_loop()
    _executor.submit(_run_research_sync, session_id, topic, loop)

    return {"session_id": session_id}


@app.websocket("/ws/research/{session_id}")
async def ws_research(websocket: WebSocket, session_id: str):
    """
    Stream live research stage updates via WebSocket.
    """
    await websocket.accept()

    try:
        get_session(session_id)
    except SessionNotFoundError:
        await websocket.send_json({"stage": "failed", "detail": f"Session '{session_id}' not found."})
        await websocket.close()
        return

    tracker = get_or_create_tracker(session_id)
    queue: asyncio.Queue = asyncio.Queue()
    tracker.subscribers.add(queue)

    try:
        # Replay any events that occurred before socket connection
        for event in tracker.events:
            await websocket.send_json(event)
            if event.get("stage") in ("research_done", "failed"):
                await websocket.close()
                return

        if tracker.is_done:
            await websocket.close()
            return

        # Stream upcoming events until completion or failure
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("stage") in ("research_done", "failed"):
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error for session %s: %s", session_id, exc)
    finally:
        tracker.subscribers.discard(queue)
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/research/{session_id}", status_code=status.HTTP_200_OK)
def get_research(session_id: str):
    """
    Return findings once research completes. Raises 409 if not completed yet.
    """
    try:
        get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    tracker = _trackers.get(session_id)
    if tracker and tracker.failed:
        raise HTTPException(
            status_code=409,
            detail=f"Research failed: {tracker.error_detail or 'Unknown error'}",
        )

    try:
        findings, citations = get_research_results(session_id)
    except InvalidSessionStateError as exc:
        raise HTTPException(status_code=409, detail=f"Research is not completed yet: {exc}")

    if hasattr(findings, "model_dump"):
        return findings.model_dump()
    elif isinstance(findings, dict):
        return findings
    return {"findings": findings}


@app.post("/research/{session_id}/qa", status_code=status.HTTP_200_OK)
def ask_question(session_id: str, body: QARequest):
    """
    Run grounded question-answering on ingested research papers.
    """
    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        record = get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    topic = record.get("research_topic") or record.get("topic") or ""
    qa_req = UserQARequest(question=body.question.strip(), topic=topic)

    try:
        response = run_user_qa(qa_req)
        if hasattr(response, "model_dump"):
            return response.model_dump()
        return response
    except Exception as exc:
        logger.exception("Q&A execution failed for session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail=f"Q&A failed: {exc}")


@app.post("/research/{session_id}/outputs", status_code=status.HTTP_200_OK)
def select_outputs_endpoint(session_id: str, body: OutputSelectionRequest):
    """
    Select desired output types and determine the next incomplete guided input tier.
    """
    if not body.output_types:
        raise HTTPException(status_code=400, detail="At least one output type is required.")

    try:
        get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        next_tier = select_outputs(session_id, body.output_types)
    except InvalidSessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tier_val = (
        next_tier.value
        if hasattr(next_tier, "value")
        else (str(next_tier) if next_tier is not None else None)
    )
    return {"next_tier": tier_val}


@app.post("/research/{session_id}/guided-input", status_code=status.HTTP_200_OK)
def submit_guided_input_endpoint(session_id: str, body: GuidedInputRequest):
    """
    Submit a guided input tier answer and check completion status.
    """
    try:
        get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        result = submit_tier(session_id, body.tier, body.value)
    except InvalidSessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    next_tier = result.get("next_tier")
    tier_val = (
        next_tier.value
        if hasattr(next_tier, "value")
        else (str(next_tier) if next_tier is not None else None)
    )

    return {
        "ok": result.get("ok", False),
        "error": result.get("error", ""),
        "next_tier": tier_val,
        "is_complete": result.get("is_complete", False),
    }


@app.post("/research/{session_id}/compose", status_code=status.HTTP_200_OK)
def compose_endpoint(session_id: str):
    """
    Trigger composition graph in a background thread using session's cached findings and bundle.
    """
    try:
        record = get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        bundle = get_bundle(session_id)
        findings, citations = get_research_results(session_id)
    except (InvalidSessionStateError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    selected_outputs = record.get("selected_outputs") or record.get("output_types")
    if not selected_outputs:
        raise HTTPException(status_code=409, detail="No output types selected for composition.")

    compose_state = {
        "request_id": session_id,
        "research_topic": record.get("research_topic") or record.get("topic"),
        "findings": findings,
        "citations": citations,
        "guided_input": bundle,
        "selected_outputs": selected_outputs,
    }

    session_store.update_status(session_id, SessionStatus.COMPOSING)
    tracker = get_or_create_tracker(session_id)
    tracker.composing = True

    _executor.submit(_run_compose_sync, session_id, compose_state)

    return {"session_id": session_id, "status": "composing"}


@app.get("/research/{session_id}/results", status_code=status.HTTP_200_OK)
def get_results_endpoint(session_id: str):
    """
    Return download URLs for all successfully composed output types.
    """
    try:
        record = get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    tracker = get_or_create_tracker(session_id)
    if tracker.composing or record.get("status") == SessionStatus.COMPOSING.value:
        raise HTTPException(status_code=409, detail="Composition is still in progress.")

    composer_results = record.get("composer_results") or tracker.composer_results
    if not composer_results:
        if record.get("status") != SessionStatus.DONE.value:
            raise HTTPException(status_code=409, detail="Composition has not been run or completed.")
        raise HTTPException(status_code=404, detail="No composer results available.")

    results_list = []
    for r in composer_results:
        if r.file_path is None:
            ot_name = getattr(r.output_type, "value", str(r.output_type))
            raise HTTPException(
                status_code=404,
                detail=f"Output file for '{ot_name}' was not generated.",
            )
        ot_str = r.output_type.value if hasattr(r.output_type, "value") else str(r.output_type)
        results_list.append({
            "output_type": ot_str,
            "download_url": f"/download/{session_id}/{ot_str}",
        })

    return results_list


@app.get("/download/{session_id}/{output_type}")
def download_file_endpoint(session_id: str, output_type: str):
    """
    Stream the rendered output document file (docx/pptx/pdf) to the client.
    """
    try:
        record = get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    tracker = get_or_create_tracker(session_id)
    composer_results = record.get("composer_results") or tracker.composer_results

    target_path = None
    for r in composer_results:
        ot_str = r.output_type.value if hasattr(r.output_type, "value") else str(r.output_type)
        if ot_str.lower() == output_type.lower():
            if r.file_path:
                target_path = Path(r.file_path)
            break

    # Fallback to backend/generated_outputs/{session_id}/{output_type}.*
    if target_path is None or not target_path.exists():
        base_gen_dir = Path(__file__).resolve().parent / "generated_outputs" / str(session_id)
        candidates = list(base_gen_dir.glob(f"{output_type.lower()}.*"))
        if candidates and candidates[0].exists():
            target_path = candidates[0]

    if target_path is None or not target_path.exists() or not target_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Output file for '{output_type}' not found for session '{session_id}'.",
        )

    suffix = target_path.suffix.lower()
    if suffix == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif suffix == ".pptx":
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    elif suffix == ".pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=target_path,
        filename=target_path.name,
        media_type=media_type,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
