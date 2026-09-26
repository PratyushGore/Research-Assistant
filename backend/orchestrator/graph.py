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

    composer_results: list[ComposerResult]

    document_review_result: Optional[DocumentReviewResult]

    user_qa_request: Optional[UserQARequest]

    user_qa_response: Optional[UserQAResponse]

    pipeline_status: Optional[PipelineStatus]

    output_type: Optional[OutputType]
# ---------------------------------------------------------------------------
# Agent Node Stubs
# Teammates should replace the body of these functions with their real logic.
# Signature to match: def agent_name(state: PipelineState) -> PipelineState
# ---------------------------------------------------------------------------

def guided_input_agent(state: PipelineState) -> PipelineState:
    print("[STUB] guided_input_agent called")
    return state


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
        return state

    if not search_results.papers:
        print("[Ingestion Agent] No papers to ingest.")
        return {
            **state,
            "ingestion_results": [],
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

        result = ingest_and_store_pdf(
            url=paper.url,
            metadata=paper,
        )

        ingestion_results.append(result)

    print(
        f"[Ingestion Agent] "
        f"{len(ingestion_results)} papers processed."
    )

    return {
        **state,
        "ingestion_results": ingestion_results,
    }


def summarization_agent(state: PipelineState) -> PipelineState:
    """
    Create FindingsPacket from the ingested research papers.

    Uses the extracted PDF text and chunks produced by the
    Ingestion Agent. This implementation does not require an
    external LLM/API.
    """

    from backend.schemas.schemas import FindingsPacket, PaperSummary, Claim

    topic = state.get("research_topic") or ""

    ingestion_results = state.get("ingestion_results")

    if not ingestion_results:
        print("[Summarization Agent] No ingestion results available.")

        return {
            **state,
            "findings": FindingsPacket(
                topic=topic,
                summaries=[],
                claims=[],
            ),
        }

    summaries = []
    all_claims = []

    for result in ingestion_results:
        metadata = result.metadata
        paper_id = result.paper_id

        # Use the extracted raw text when available.
        raw_text = result.raw_text or ""

        # Fallback to joining chunks if raw_text is unavailable.
        if not raw_text and result.chunks:
            raw_text = " ".join(
                chunk.text
                for chunk in result.chunks
                if chunk.text
            )

        if not raw_text:
            print(
                f"[Summarization Agent] "
                f"No text available for {paper_id}"
            )

            summaries.append(
                PaperSummary(
                    paper_id=paper_id,
                    summary="No text could be extracted from this paper.",
                    key_findings=[],
                    extracted_claims=[],
                )
            )
            continue

        # Keep the summary deterministic and lightweight for now.
        # The first portion provides a concise representation of the
        # extracted paper text without requiring an external LLM.
        summary_text = raw_text[:1500].strip()

        if len(raw_text) > 1500:
            summary_text += "..."

        # Create a small set of source-grounded claims from chunks.
        paper_claims = []

        for index, chunk in enumerate(result.chunks[:3]):
            if not chunk.text.strip():
                continue

            claim = Claim(
                claim_id=f"{paper_id}:claim:{index}",
                text=chunk.text[:500].strip(),
                source_paper_id=paper_id,
                source_chunk_ids=[chunk.chunk_id],
                verification_status="pending",
                revision_attempts=0,
            )

            paper_claims.append(claim)
            all_claims.append(claim)

        # Basic key findings from the first few chunks.
        key_findings = [
            chunk.text[:300].strip()
            for chunk in result.chunks[:3]
            if chunk.text.strip()
        ]

        summary = PaperSummary(
            paper_id=paper_id,
            summary=summary_text,
            key_findings=key_findings,
            extracted_claims=paper_claims,
        )

        summaries.append(summary)

        print(
            f"[Summarization Agent] "
            f"Processed: {metadata.title}"
        )

    findings = FindingsPacket(
        topic=topic,
        summaries=summaries,
        claims=all_claims,
    )

    print(
        f"[Summarization Agent] "
        f"Created {len(summaries)} paper summaries "
        f"and {len(all_claims)} claims."
    )

    return {
        **state,
        "findings": findings,
    }
   
def verification_agent(state: PipelineState) -> PipelineState:
    """
    Verify extracted claims against the source chunks from ingestion.

    This is a deterministic, source-grounded verification step.
    It does not require an external LLM/API.
    """

    from backend.schemas.schemas import VerificationResult

    findings = state.get("findings")
    ingestion_results = state.get("ingestion_results")

    if findings is None:
        print("[Verification Agent] No findings available.")

        return {
            **state,
            "verification_results": [],
        }

    if not ingestion_results:
        print("[Verification Agent] No ingestion results available.")

        return {
            **state,
            "verification_results": [],
        }

    # Build a lookup of chunk_id -> chunk text.
    chunk_lookup = {}

    for ingestion_result in ingestion_results:
        for chunk in ingestion_result.chunks:
            chunk_lookup[chunk.chunk_id] = chunk.text

    verification_results = []

    print(
        f"[Verification Agent] "
        f"Verifying {len(findings.claims)} claims."
    )

    for claim in findings.claims:
        supporting_chunk_ids = [
            chunk_id
            for chunk_id in claim.source_chunk_ids
            if chunk_id in chunk_lookup
        ]

        if not supporting_chunk_ids:
            verification_results.append(
                VerificationResult(
                    claim_id=claim.claim_id,
                    verification_status="unsupported",
                    confidence_score=0.0,
                    explanation=(
                        "No supporting source chunk was found "
                        "for this claim."
                    ),
                    supporting_chunk_ids=[],
                )
            )
            continue

        # Check whether the claim text is represented in its
        # source chunk. This keeps verification deterministic.
        claim_text = claim.text.strip().lower()

        supporting_text = " ".join(
            chunk_lookup[chunk_id]
            for chunk_id in supporting_chunk_ids
        ).lower()

        if claim_text and claim_text[:200] in supporting_text:
            verification_status = "verified"
            confidence_score = 1.0
            explanation = (
                "The claim is directly supported by "
                "its source chunk."
            )
        else:
            verification_status = "partially_supported"
            confidence_score = 0.5
            explanation = (
                "A supporting source chunk exists, but the "
                "claim text was not found verbatim in that chunk."
            )

        verification_results.append(
            VerificationResult(
                claim_id=claim.claim_id,
                verification_status=verification_status,
                confidence_score=confidence_score,
                explanation=explanation,
                supporting_chunk_ids=supporting_chunk_ids,
            )
        )

    print(
        f"[Verification Agent] "
        f"{len(verification_results)} claims verified."
    )

    return {
        **state,
        "verification_results": verification_results,
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


def composer_agent(state: PipelineState) -> PipelineState:
    """Run the Composer Agent using the verified research findings."""

    from backend.agents.composer.agent import composer_agent as composer

    findings = state.get("findings")
    citation_result = state.get("citations")
    guided_input = state.get("guided_input")

    if findings is None:
        print("[Composer Agent] No findings available.")
        return state

    if citation_result is None:
        print("[Composer Agent] No citation results available.")
        return state

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

    output_type = state.get(
        "output_type",
        OutputType.LITERATURE_SURVEY,
    )

    print(
        f"[Composer Agent] Creating "
        f"{output_type.value}..."
    )

    result = composer.compose(
        output_type=output_type,
        guided_input=guided_input,
        findings=findings,
        citation_result=citation_result,
    )

    print(
        f"[Composer Agent] Created output: "
        f"{result.title}"
    )

    return {
        **state,
        "guided_input": guided_input,
        "composer_results": [result],
    }


def document_review_agent(state: PipelineState) -> PipelineState:
    print("[STUB] document_review_agent called")
    return state


def user_qa_agent(state: PipelineState) -> PipelineState:
    print("[STUB] user_qa_agent called")
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
builder.add_node("document_review", document_review_agent)

# Wire the primary linear pipeline
builder.add_edge(START, "guided_input")
builder.add_edge("guided_input", "search")
builder.add_edge("search", "ingestion")
builder.add_edge("ingestion", "summarization")
builder.add_edge("summarization", "verification")
builder.add_edge("verification", "citation")
builder.add_edge("citation", "composer")
builder.add_edge("composer", END)

# Document review terminal edge in main graph structure
builder.add_edge("document_review", END)

# Compiled main pipeline executable
graph = builder.compile()


# ---------------------------------------------------------------------------
# Standalone QA Entry Point Graph
# Allows invoking QA directly at any time as an independent entry point.
# ---------------------------------------------------------------------------

qa_builder = StateGraph(PipelineState)
qa_builder.add_node("user_qa", user_qa_agent)
qa_builder.add_edge(START, "user_qa")
qa_builder.add_edge("user_qa", END)

qa_graph = qa_builder.compile()
