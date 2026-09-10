from typing import Optional, TypedDict
from langgraph.graph import StateGraph, START, END

from backend.schemas.schemas import (
    GuidedInputBundle,
    SearchResult,
    IngestionResult,
    FindingsPacket,
    VerificationResult,
    CitationResult,
    ComposerResult,
    QARequest,
    QAResponse,
    PipelineStatus,
)


class PipelineState(TypedDict, total=False):
    """Shared state passed between LangGraph agent nodes."""
    request_id: str
    guided_input: Optional[GuidedInputBundle]
    search_results: Optional[SearchResult]
    ingestion_results: Optional[list[IngestionResult]]
    findings: Optional[FindingsPacket]
    verification_results: Optional[list[VerificationResult]]
    citations: Optional[CitationResult]
    composer_results: Optional[list[ComposerResult]]
    qa_request: Optional[QARequest]
    qa_response: Optional[QAResponse]
    status: Optional[PipelineStatus]


# ---------------------------------------------------------------------------
# Agent Node Stubs
# Teammates should replace the body of these functions with their real logic.
# Signature to match: def agent_name(state: PipelineState) -> PipelineState
# ---------------------------------------------------------------------------

def guided_input_agent(state: PipelineState) -> PipelineState:
    print("[STUB] guided_input_agent called")
    return state


def search_agent(state: PipelineState) -> PipelineState:
    print("[STUB] search_agent called")
    return state


def ingestion_agent(state: PipelineState) -> PipelineState:
    print("[STUB] ingestion_agent called")
    return state


def summarization_agent(state: PipelineState) -> PipelineState:
    print("[STUB] summarization_agent called")
    return state


def verification_agent(state: PipelineState) -> PipelineState:
    print("[STUB] verification_agent called")
    return state


def citation_agent(state: PipelineState) -> PipelineState:
    print("[STUB] citation_agent called")
    return state


def composer_agent(state: PipelineState) -> PipelineState:
    print("[STUB] composer_agent called")
    return state


def qa_agent(state: PipelineState) -> PipelineState:
    print("[STUB] qa_agent called")
    return state


# ---------------------------------------------------------------------------
# Main Pipeline Graph Construction
# Linear Flow: guided_input -> search -> ingestion -> summarization ->
#              verification -> citation -> composer
# ---------------------------------------------------------------------------

builder = StateGraph(PipelineState)

# Register agent nodes
builder.add_node("guided_input", guided_input_agent)
builder.add_node("search", search_agent)
builder.add_node("ingestion", ingestion_agent)
builder.add_node("summarization", summarization_agent)
builder.add_node("verification", verification_agent)
builder.add_node("citation", citation_agent)
builder.add_node("composer", composer_agent)
builder.add_node("qa", qa_agent)

# Wire the primary linear pipeline
builder.add_edge(START, "guided_input")
builder.add_edge("guided_input", "search")
builder.add_edge("search", "ingestion")
builder.add_edge("ingestion", "summarization")
builder.add_edge("summarization", "verification")
builder.add_edge("verification", "citation")
builder.add_edge("citation", "composer")
builder.add_edge("composer", END)

# QA terminal edge in main graph structure
builder.add_edge("qa", END)

# Compiled main pipeline executable
graph = builder.compile()


# ---------------------------------------------------------------------------
# Standalone QA Entry Point Graph
# Allows invoking QA directly at any time as an independent entry point.
# ---------------------------------------------------------------------------

qa_builder = StateGraph(PipelineState)
qa_builder.add_node("qa", qa_agent)
qa_builder.add_edge(START, "qa")
qa_builder.add_edge("qa", END)

qa_graph = qa_builder.compile()
