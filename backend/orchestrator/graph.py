import operator
from typing import Annotated, Any, Callable, Optional, TypedDict
from langgraph.graph import StateGraph, START, END

from backend.schemas.schemas import (
    GuidedInputBundle,
    SearchResult,
    IngestionResult,
    FindingsPacket,
    VerificationResult,
    CitationResult,
    ComposerResult,
    DocumentReviewRequest,
    DocumentReviewResult,
    UserQARequest,
    UserQAResponse,
    PipelineStatus,
    OutputType,
)


class PipelineState(TypedDict, total=False):
    """Shared state passed between LangGraph agent nodes."""

    request_id: str

    research_topic: Optional[str]

    guided_input: Optional[GuidedInputBundle]

    search_results: Optional[SearchResult]

    ingestion_results: list[IngestionResult]

    findings: Optional[FindingsPacket]

    verification_results: list[VerificationResult]

    citations: Optional[CitationResult]

    composer_results: Annotated[list[ComposerResult], operator.add]

    document_review_result: Optional[DocumentReviewResult]

    user_qa_request: Optional[UserQARequest]

    user_qa_response: Optional[UserQAResponse]

    pipeline_status: Optional[PipelineStatus]

    output_type: Optional[OutputType]

    selected_outputs: list[OutputType]


# ---------------------------------------------------------------------------
# Agent Node Functions
# ---------------------------------------------------------------------------

def guided_input_agent(state: PipelineState) -> dict[str, Any]:
    """Pass-through node that checks for guided_input and changes nothing."""
    if not state.get("guided_input"):
        print("[Guided Input Agent] Warning: guided_input is missing from state.")
    return {}


def search_agent(state: PipelineState) -> PipelineState:
    """Run the Search Agent using the research topic from pipeline state."""

    from backend.agents.search.agent import search_papers

    topic = state.get("research_topic")

    if not topic:
        print("[Search Agent] No research topic provided.")
        return state

    print(f"[Search Agent] Searching for: {topic}")

    search_result = search_papers(
        topic,
        max_results_per_source=5,
    )

    print(
        f"[Search Agent] Found {search_result.total_results} papers."
    )

    if not search_result.papers:
        return {
            **state,
            "search_results": search_result,
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="No papers found for this topic.",
            ),
        }

    return {
        **state,
        "search_results": search_result,
    }


def ingestion_agent(state: PipelineState) -> PipelineState:
    """Run Person A's Ingestion Agent for the papers returned by Search."""

    from backend.agents.ingestion.agent import ingest_and_store_pdf

    search_results = state.get("search_results")

    if search_results is None:
        print("[Ingestion Agent] No search results available.")
        return {
            **state,
            "ingestion_results": [],
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="No papers to ingest.",
            ),
        }

    if not search_results.papers:
        print("[Ingestion Agent] No papers to ingest.")
        return {
            **state,
            "ingestion_results": [],
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="No papers to ingest.",
            ),
        }

    ingestion_results = []

    for paper in search_results.papers:
        if not paper.url:
            print(
                f"[Ingestion Agent] Skipping {paper.paper_id}: "
                "no PDF URL available."
            )
            continue

        print(
            f"[Ingestion Agent] Ingesting: "
            f"{paper.title}"
        )

        try:
            result = ingest_and_store_pdf(
                url=paper.url,
                metadata=paper,
            )

            if result and (result.chunks or result.raw_text):
                ingestion_results.append(result)
            else:
                print(
                    f"[Ingestion Agent] Ingestion yielded no content for: {paper.title}"
                )
        except Exception as exc:
            print(
                f"[Ingestion Agent] Failed to ingest {paper.paper_id}: {exc}"
            )

    print(
        f"[Ingestion Agent] "
        f"{len(ingestion_results)} papers processed."
    )

    if not ingestion_results:
        return {
            **state,
            "ingestion_results": [],
            "pipeline_status": PipelineStatus(
                stage="failed",
                detail="All papers failed during ingestion.",
            ),
        }

    return {
        **state,
        "ingestion_results": ingestion_results,
    }


def summarization_agent(state: PipelineState) -> PipelineState:
    """Run Person B's Summarization Agent (Gemini-powered, map-reduce)."""
    from backend.agents.summarization.agent import run_summarization
    from backend.schemas.schemas import FindingsPacket

    guided_input = state.get("guided_input")
    topic = state.get("research_topic") or (
        guided_input.cover_info.title if guided_input else ""
    )
    ingestion_results = state.get("ingestion_results")

    if not ingestion_results:
        print("[Summarization Agent] No ingestion results available.")
        return {
            **state,
            "findings": FindingsPacket(topic=topic, summaries=[], claims=[]),
        }

    findings = run_summarization(topic, ingestion_results)

    print(
        f"[Summarization Agent] Created {len(findings.summaries)} paper "
        f"summaries and {len(findings.claims)} claims."
    )

    return {**state, "findings": findings}


def verification_agent(state: PipelineState) -> PipelineState:
    """Run Person B's Verification Agent (RAG-grounding, bounded revise loop)."""
    from backend.agents.verification.agent import run_verification

    findings = state.get("findings")
    ingestion_results = state.get("ingestion_results")

    if findings is None or not ingestion_results:
        print("[Verification Agent] No findings/ingestion results available.")
        return {**state, "verification_results": []}

    verification_results, updated_findings = run_verification(findings, ingestion_results)

    print(f"[Verification Agent] {len(verification_results)} claims verified.")

    # updated_findings carries revised claim text / revision_attempts /
    # verification_status back onto the same Claim objects.
    return {
        **state,
        "verification_results": verification_results,
        "findings": updated_findings,
    }


def citation_agent(state: PipelineState) -> PipelineState:
    """
    Create formatted citations and a bibliography from the
    papers contained in the FindingsPacket.
    """

    from backend.schemas.schemas import (
        CitationResult,
        FormattedCitation,
    )

    findings = state.get("findings")

    if findings is None:
        print("[Citation Agent] No findings available.")

        return {
            **state,
            "citations": CitationResult(
                citation_style="APA",
                citations=[],
                bibliography=[],
            ),
        }

    citation_style = "APA"

    citations = []
    bibliography = []

    # Avoid creating duplicate citations for the same paper.
    seen_papers = set()

    for index, summary in enumerate(findings.summaries, start=1):
        paper_id = summary.paper_id

        if paper_id in seen_papers:
            continue

        seen_papers.add(paper_id)

        # Find the original paper metadata from ingestion results.
        metadata = None

        for ingestion_result in state.get("ingestion_results", []):
            if ingestion_result.paper_id == paper_id:
                metadata = ingestion_result.metadata
                break

        if metadata is None:
            print(
                f"[Citation Agent] Metadata not found for {paper_id}"
            )
            continue

        title = metadata.title or "Untitled paper"

        authors = metadata.authors or []

        # Format authors for a simple APA-style bibliography.
        if authors:
            author_text = ", ".join(authors)
        else:
            author_text = "Unknown author"

        year = metadata.year or "n.d."

        venue = metadata.venue or ""

        # Build the bibliography entry.
        bibliography_entry = (
            f"{author_text} ({year}). {title}."
        )

        if venue:
            bibliography_entry += f" {venue}."

        if metadata.url:
            bibliography_entry += f" {metadata.url}"

        citation_id = f"citation:{paper_id}"

        inline_marker = f"[{index}]"

        formatted_citation = FormattedCitation(
            citation_id=citation_id,
            paper_id=paper_id,
            citation_style=citation_style,
            inline_marker=inline_marker,
            full_entry=bibliography_entry,
        )

        citations.append(formatted_citation)
        bibliography.append(bibliography_entry)

        print(
            f"[Citation Agent] Created citation for: {title}"
        )

    citation_result = CitationResult(
        citation_style=citation_style,
        citations=citations,
        bibliography=bibliography,
    )

    print(
        f"[Citation Agent] Created "
        f"{len(citations)} citations."
    )

    return {
        **state,
        "citations": citation_result,
    }


def _run_composer(
    state: PipelineState,
    output_type: OutputType | str,
) -> dict[str, list[ComposerResult]]:
    """
    Shared helper for composer nodes.
    Reuses existing Composer logic and returns only the composer_results delta.
    """
    from backend.agents.composer.agent import composer_agent as composer

    if isinstance(output_type, str):
        output_type = OutputType(output_type)

    findings = state.get("findings")
    citation_result = state.get("citations")
    guided_input = state.get("guided_input")

    if findings is None:
        print(f"[Composer Agent] No findings available for {output_type.value}.")
        return {"composer_results": []}

    if citation_result is None:
        print(f"[Composer Agent] No citation results available for {output_type.value}.")
        return {"composer_results": []}

    # Create a default GuidedInputBundle if the guided-input
    # agent has not populated one yet.
    if guided_input is None:
        from backend.schemas.schemas import (
            CoverInfo,
            GuidedInputBundle,
        )

        topic = state.get(
            "research_topic",
            findings.topic,
        )

        guided_input = GuidedInputBundle(
            cover_info=CoverInfo(
                title=topic,
                subtitle="Research Report",
            )
        )

    print(f"[Composer Agent] Creating {output_type.value}...")

    result = composer.compose(
        output_type=output_type,
        guided_input=guided_input,
        findings=findings,
        citation_result=citation_result,
    )

    print(f"[Composer Agent] Created output: {result.title}")

    # Render output file
    import logging
    from pathlib import Path
    from backend.agents.output_renderer.renderer import render_output

    logger = logging.getLogger(__name__)

    default_formats: dict[OutputType, str] = {
        OutputType.LITERATURE_SURVEY: "docx",
        OutputType.EXECUTIVE_SUMMARY: "docx",
        OutputType.RESEARCH_PAPER: "docx",
        OutputType.PPT: "pptx",
    }
    output_format = default_formats.get(output_type, "docx")
    ext = output_format

    request_id = state.get("request_id") or "default"
    generated_dir = Path(__file__).resolve().parent.parent / "generated_outputs" / str(request_id)

    try:
        generated_dir.mkdir(parents=True, exist_ok=True)
        output_file_path = generated_dir / f"{output_type.value}.{ext}"
        rendered_path = render_output(
            composer_result=result,
            output_format=output_format,
            output_path=output_file_path,
        )
        result.file_path = str(rendered_path)
        print(f"[Composer Agent] Rendered {output_type.value} to {rendered_path}")
    except Exception as exc:
        logger.warning(
            f"[Composer Agent] Failed to render output for {output_type.value}: {exc}",
            exc_info=True,
        )
        result.file_path = None

    return {"composer_results": [result]}


def composer_literature_survey(state: PipelineState) -> dict[str, list[ComposerResult]]:
    return _run_composer(state, OutputType.LITERATURE_SURVEY)


def composer_executive_summary(state: PipelineState) -> dict[str, list[ComposerResult]]:
    return _run_composer(state, OutputType.EXECUTIVE_SUMMARY)


def composer_ppt(state: PipelineState) -> dict[str, list[ComposerResult]]:
    return _run_composer(state, OutputType.PPT)


def composer_research_paper(state: PipelineState) -> dict[str, list[ComposerResult]]:
    return _run_composer(state, OutputType.RESEARCH_PAPER)


def composer_agent(state: PipelineState) -> dict[str, list[ComposerResult]]:
    output_type = state.get("output_type") or OutputType.LITERATURE_SURVEY
    return _run_composer(state, output_type)


COMPOSER_NODES: dict[OutputType, str] = {
    OutputType.LITERATURE_SURVEY: "composer_literature_survey",
    OutputType.EXECUTIVE_SUMMARY: "composer_executive_summary",
    OutputType.PPT: "composer_ppt",
    OutputType.RESEARCH_PAPER: "composer_research_paper",
}


def should_continue_after_search(state: PipelineState) -> str:
    """
    Router determining whether to continue after search.
    Returns 'stop' if pipeline_status with stage == 'failed' is set, else 'continue'.
    """
    status = state.get("pipeline_status")
    if status is not None:
        stage = getattr(status, "stage", None)
        if stage is None and isinstance(status, dict):
            stage = status.get("stage")
        if stage == "failed":
            return "stop"
    return "continue"


def should_continue_after_ingestion(state: PipelineState) -> str:
    """
    Router determining whether to continue after ingestion.
    Returns 'stop' if pipeline_status with stage == 'failed' is set, else 'continue'.
    """
    status = state.get("pipeline_status")
    if status is not None:
        stage = getattr(status, "stage", None)
        if stage is None and isinstance(status, dict):
            stage = status.get("stage")
        if stage == "failed":
            return "stop"
    return "continue"


def route_to_composers(state: PipelineState) -> list[str]:
    """
    Pure routing function that determines which composer nodes to execute.
    Returns node names deduplicated and in order.
    Falls back to [output_type or OutputType.LITERATURE_SURVEY] if selected_outputs is missing/empty.
    """
    selected = state.get("selected_outputs")
    if not selected:
        fallback = state.get("output_type") or OutputType.LITERATURE_SURVEY
        selected = [fallback]

    node_names: list[str] = []
    seen: set[str] = set()

    for item in selected:
        try:
            norm_type = item if isinstance(item, OutputType) else OutputType(item)
        except (ValueError, TypeError):
            continue

        node_name = COMPOSER_NODES.get(norm_type)
        if node_name and node_name not in seen:
            seen.add(node_name)
            node_names.append(node_name)

    return node_names


def document_review_agent(state: PipelineState) -> PipelineState:
    print("[STUB] document_review_agent called")
    return state


def user_qa_agent(state: PipelineState) -> PipelineState:
    print("[STUB] user_qa_agent called")
    return state


# ---------------------------------------------------------------------------
# Main Pipeline Graph Construction
# Linear Flow: guided_input -> search -> ingestion -> summarization ->
#              verification -> citation -> parallel composers (conditional) -> END
# ---------------------------------------------------------------------------

def build_pipeline_graph(
    node_overrides: Optional[dict[str, Callable]] = None,
):
    """
    Build and compile the main pipeline graph.
    Accepts node_overrides so tests can inject fake nodes.
    """
    overrides = node_overrides or {}

    builder = StateGraph(PipelineState)

    # Register linear agent nodes
    builder.add_node("guided_input", overrides.get("guided_input", guided_input_agent))
    builder.add_node("search", overrides.get("search", search_agent))
    builder.add_node("ingestion", overrides.get("ingestion", ingestion_agent))
    builder.add_node("summarization", overrides.get("summarization", summarization_agent))
    builder.add_node("verification", overrides.get("verification", verification_agent))
    builder.add_node("citation", overrides.get("citation", citation_agent))

    # Register parallel composer nodes
    builder.add_node(
        "composer_literature_survey",
        overrides.get("composer_literature_survey", composer_literature_survey),
    )
    builder.add_node(
        "composer_executive_summary",
        overrides.get("composer_executive_summary", composer_executive_summary),
    )
    builder.add_node(
        "composer_ppt",
        overrides.get("composer_ppt", composer_ppt),
    )
    builder.add_node(
        "composer_research_paper",
        overrides.get("composer_research_paper", composer_research_paper),
    )

    # Document review stub (unwired to pipeline, terminal edge to END)
    builder.add_node(
        "document_review",
        overrides.get("document_review", document_review_agent),
    )

    # Wire the primary linear pipeline up to citation with conditional failure routing
    builder.add_edge(START, "guided_input")
    builder.add_edge("guided_input", "search")
    builder.add_conditional_edges(
        "search",
        should_continue_after_search,
        {
            "continue": "ingestion",
            "stop": END,
        },
    )
    builder.add_conditional_edges(
        "ingestion",
        should_continue_after_ingestion,
        {
            "continue": "summarization",
            "stop": END,
        },
    )
    builder.add_edge("summarization", "verification")
    builder.add_edge("verification", "citation")

    # Conditional fan-out from citation to selected composer nodes
    composer_node_names = [
        "composer_literature_survey",
        "composer_executive_summary",
        "composer_ppt",
        "composer_research_paper",
    ]
    builder.add_conditional_edges(
        "citation",
        route_to_composers,
        composer_node_names,
    )

    # Every composer node then goes to END
    builder.add_edge("composer_literature_survey", END)
    builder.add_edge("composer_executive_summary", END)
    builder.add_edge("composer_ppt", END)
    builder.add_edge("composer_research_paper", END)

    # Document review terminal edge in main graph structure
    builder.add_edge("document_review", END)

    return builder.compile()


# Compiled main pipeline executable (backward compatibility)
graph = build_pipeline_graph()


# ---------------------------------------------------------------------------
# Decoupled Research and Compose Graphs
# ---------------------------------------------------------------------------

def build_research_graph(
    node_overrides: Optional[dict[str, Callable]] = None,
):
    """
    Build and compile the research-only graph.
    Flow: START -> search -> (conditional: stop on failure -> END, else continue) ->
          ingestion -> (conditional: stop on failure -> END, else continue) ->
          summarization -> verification -> citation -> END.
    Accepts node_overrides so tests can inject fake nodes.
    """
    overrides = node_overrides or {}

    builder = StateGraph(PipelineState)

    builder.add_node("search", overrides.get("search", search_agent))
    builder.add_node("ingestion", overrides.get("ingestion", ingestion_agent))
    builder.add_node("summarization", overrides.get("summarization", summarization_agent))
    builder.add_node("verification", overrides.get("verification", verification_agent))
    builder.add_node("citation", overrides.get("citation", citation_agent))

    builder.add_edge(START, "search")
    builder.add_conditional_edges(
        "search",
        should_continue_after_search,
        {
            "continue": "ingestion",
            "stop": END,
        },
    )
    builder.add_conditional_edges(
        "ingestion",
        should_continue_after_ingestion,
        {
            "continue": "summarization",
            "stop": END,
        },
    )
    builder.add_edge("summarization", "verification")
    builder.add_edge("verification", "citation")
    builder.add_edge("citation", END)

    return builder.compile()


def build_compose_graph(
    node_overrides: Optional[dict[str, Callable]] = None,
):
    """
    Build and compile the document composition graph.
    Flow: START -> guided_input -> (conditional fan-out via route_to_composers) ->
          composer nodes -> END.
    Accepts node_overrides so tests can inject fake nodes.
    """
    overrides = node_overrides or {}

    builder = StateGraph(PipelineState)

    builder.add_node("guided_input", overrides.get("guided_input", guided_input_agent))
    builder.add_node(
        "composer_literature_survey",
        overrides.get("composer_literature_survey", composer_literature_survey),
    )
    builder.add_node(
        "composer_executive_summary",
        overrides.get("composer_executive_summary", composer_executive_summary),
    )
    builder.add_node(
        "composer_ppt",
        overrides.get("composer_ppt", composer_ppt),
    )
    builder.add_node(
        "composer_research_paper",
        overrides.get("composer_research_paper", composer_research_paper),
    )

    builder.add_edge(START, "guided_input")

    composer_node_names = [
        "composer_literature_survey",
        "composer_executive_summary",
        "composer_ppt",
        "composer_research_paper",
    ]
    builder.add_conditional_edges(
        "guided_input",
        route_to_composers,
        composer_node_names,
    )

    builder.add_edge("composer_literature_survey", END)
    builder.add_edge("composer_executive_summary", END)
    builder.add_edge("composer_ppt", END)
    builder.add_edge("composer_research_paper", END)

    return builder.compile()


# Compiled research and compose graph executables
research_graph = build_research_graph()
compose_graph = build_compose_graph()


# ---------------------------------------------------------------------------
# Standalone QA Entry Point Graph
# Allows invoking QA directly at any time as an independent entry point.
# ---------------------------------------------------------------------------

qa_builder = StateGraph(PipelineState)
qa_builder.add_node("user_qa", user_qa_agent)
qa_builder.add_edge(START, "user_qa")
qa_builder.add_edge("user_qa", END)

qa_graph = qa_builder.compile()
