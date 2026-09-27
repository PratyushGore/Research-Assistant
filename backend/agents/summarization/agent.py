"""
Summarization Agent (Person B).

Produces a per-paper summary + extracted, chunk-grounded claims for every
ingested paper, then runs a cross-paper synthesis pass (the "reduce" step
of map-reduce) that is used internally to sanity-check coverage and feed
the Verification Agent's contradiction check.

Schema contract: this module returns a FindingsPacket exactly as locked in
backend/schemas/schemas.py. It never adds or renames fields.

See ASSUMPTIONS.md for documented decisions on:
  #1 - how "relevant chunks per paper" are selected (keyword-overlap
       ranking over Person A's ingested chunks, standing in for a direct
       topic-query against ChromaDB)
  #2 - where the cross-paper synthesis text lives (not persisted in the
       locked FindingsPacket - no field exists for it; logged instead)
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from backend.agents.common.llm_client import GeminiClient
from backend.schemas.schemas import Claim, FindingsPacket, IngestionResult, PaperSummary

logger = logging.getLogger("research_assistant.summarization")

AGENT_NAME = "summarization_agent"
TOP_K_CHUNKS = 6
MAX_CLAIMS_PER_PAPER = 5


def _select_relevant_chunks(topic: str, ingestion_result: IngestionResult, k: int = TOP_K_CHUNKS):
    """Rank this paper's chunks by keyword overlap with the topic; top-k. See ASSUMPTIONS.md #1."""
    if not ingestion_result.chunks:
        return []

    topic_terms = set(re.findall(r"[a-zA-Z]{3,}", topic.lower()))
    if not topic_terms:
        return ingestion_result.chunks[:k]

    def score(chunk_text: str) -> int:
        terms = set(re.findall(r"[a-zA-Z]{3,}", chunk_text.lower()))
        return len(terms & topic_terms)

    ranked = sorted(ingestion_result.chunks, key=lambda c: score(c.text or ""), reverse=True)
    return ranked[:k] if score(ranked[0].text or "") > 0 else ingestion_result.chunks[:k]


def _summarize_paper(client: GeminiClient, topic: str, ingestion_result: IngestionResult) -> PaperSummary:
    paper_id = ingestion_result.paper_id
    chunks = _select_relevant_chunks(topic, ingestion_result)

    if not chunks:
        return PaperSummary(
            paper_id=paper_id,
            summary="No text could be extracted from this paper.",
            key_findings=[],
            extracted_claims=[],
        )

    context = "\n\n".join(f"[chunk_id={c.chunk_id}] {c.text.strip()}" for c in chunks if c.text)

    prompt = f"""You are a careful research-paper summarizer.
Research topic: {topic}
Paper title: {ingestion_result.metadata.title}

Below are the most relevant excerpts retrieved from this paper. Using ONLY
these excerpts (no outside knowledge), respond in exactly this format:

SUMMARY: <3-5 sentence summary of what this paper found, relevant to the topic>
KEY_FINDINGS:
- <finding 1>
- <finding 2>
- <finding 3 (optional)>
CLAIMS:
- claim: <one specific, checkable factual claim from the excerpts> | chunk_id: <the chunk_id it came from>
- claim: <...> | chunk_id: <...>
(up to {MAX_CLAIMS_PER_PAPER} claims. Each claim MUST be traceable to exactly one chunk_id listed above.)

Excerpts:
{context}
"""

    raw = client.generate(prompt, paper_id=paper_id, agent_name=AGENT_NAME, purpose="per_paper_summary_and_claims")
    return _parse_summary_response(paper_id, raw, chunks)


def _parse_summary_response(paper_id: str, raw: str, chunks) -> PaperSummary:
    """Parse the structured Gemini response into schema objects, failing gracefully."""
    valid_chunk_ids = {c.chunk_id for c in chunks}
    summary_text = ""
    key_findings: List[str] = []
    claims: List[Claim] = []

    try:
        summary_match = re.search(r"SUMMARY:\s*(.+?)(?:\nKEY_FINDINGS:|\Z)", raw, re.S)
        if summary_match:
            summary_text = summary_match.group(1).strip()

        findings_match = re.search(r"KEY_FINDINGS:\s*(.+?)(?:\nCLAIMS:|\Z)", raw, re.S)
        if findings_match:
            key_findings = [
                line.strip("- ").strip()
                for line in findings_match.group(1).splitlines()
                if line.strip().startswith("-")
            ]

        claims_match = re.search(r"CLAIMS:\s*(.+)\Z", raw, re.S)
        if claims_match:
            for i, line in enumerate(claims_match.group(1).splitlines()):
                line = line.strip()
                if not line.startswith("-"):
                    continue
                m = re.match(r"-\s*claim:\s*(.+?)\s*\|\s*chunk_id:\s*(\S+)", line)
                if not m:
                    continue
                claim_text, chunk_id = m.group(1).strip(), m.group(2).strip()
                # Only accept claims traceable to a chunk we actually retrieved -
                # this is what the Verification Agent's grounding check relies on.
                if chunk_id not in valid_chunk_ids:
                    logger.warning(
                        "[%s] Dropping claim for paper=%s: chunk_id %s not in retrieved set",
                        AGENT_NAME, paper_id, chunk_id,
                    )
                    continue
                claims.append(
                    Claim(
                        claim_id=f"{paper_id}:claim:{i}",
                        text=claim_text,
                        source_paper_id=paper_id,
                        source_chunk_ids=[chunk_id],
                        verification_status="pending",
                        revision_attempts=0,
                    )
                )
    except Exception:
        logger.exception("[%s] Failed to parse LLM response for paper=%s", AGENT_NAME, paper_id)

    if not summary_text:
        summary_text = raw[:500].strip() or "Summary unavailable."

    return PaperSummary(
        paper_id=paper_id,
        summary=summary_text,
        key_findings=key_findings[:5],
        extracted_claims=claims[:MAX_CLAIMS_PER_PAPER],
    )


def _cross_paper_synthesis(client: GeminiClient, topic: str, summaries: List[PaperSummary]) -> str:
    """
    Reduce step of map-reduce: synthesize a short cross-paper narrative from
    the per-paper summaries. Not persisted in FindingsPacket - no field
    exists for it in the locked schema (ASSUMPTIONS.md #2) - logged here so
    it's available for the final report / viva.
    """
    if not summaries:
        return ""

    joined = "\n\n".join(f"[{s.paper_id}] {s.summary}" for s in summaries)
    prompt = f"""Research topic: {topic}
Below are independent per-paper summaries. In 4-6 sentences, synthesize the
cross-paper findings: what do these papers collectively say, where do they
agree, and where might they disagree? Do not invent facts not present below.

{joined}
"""
    synthesis = client.generate(prompt, paper_id="__cross_paper__", agent_name=AGENT_NAME, purpose="cross_paper_synthesis")
    logger.info("[%s] Cross-paper synthesis: %s", AGENT_NAME, synthesis)
    return synthesis


def revise_claim(client: GeminiClient, claim: Claim, chunk_text: str, judge_feedback: str) -> Claim:
    """
    Called by the Verification Agent when a claim fails the grounding check.
    Rewrites the claim so it is strictly supported by chunk_text, given the
    judge's feedback. Never invents a new claim - only revises this one's text.
    """
    prompt = f"""The following claim was flagged as NOT clearly supported by its source text.

Claim: {claim.text}
Source text: {chunk_text}
Why it failed verification: {judge_feedback}

Rewrite the claim so it is a precise, narrower statement that IS directly
supported by the source text above. If no part of the source text supports
any version of this claim, respond with exactly: UNSUPPORTABLE
Respond with only the revised claim text (or UNSUPPORTABLE), nothing else.
"""
    revised_text = client.generate(
        prompt, paper_id=claim.source_paper_id, agent_name=AGENT_NAME, purpose="claim_revision"
    ).strip()

    if not revised_text or revised_text.upper() == "UNSUPPORTABLE":
        return claim  # leave unchanged; Verification Agent's loop cap will mark it "unverified"

    return claim.model_copy(update={"text": revised_text})


def run_summarization(
    topic: str,
    ingestion_results: List[IngestionResult],
    client: Optional[GeminiClient] = None,
) -> FindingsPacket:
    """Entry point called from graph.py's summarization_agent node."""
    client = client or GeminiClient()

    if not ingestion_results:
        logger.info("[%s] No ingestion results available.", AGENT_NAME)
        return FindingsPacket(topic=topic, summaries=[], claims=[])

    summaries: List[PaperSummary] = []
    all_claims: List[Claim] = []

    for result in ingestion_results:
        try:
            summary = _summarize_paper(client, topic, result)
        except Exception:
            logger.exception("[%s] Failed to summarize paper=%s - failing gracefully", AGENT_NAME, result.paper_id)
            summary = PaperSummary(
                paper_id=result.paper_id,
                summary="Summarization failed for this paper (see logs).",
                key_findings=[],
                extracted_claims=[],
            )
        summaries.append(summary)
        all_claims.extend(summary.extracted_claims)

    _cross_paper_synthesis(client, topic, summaries)

    logger.info("[%s] Created %d paper summaries and %d claims.", AGENT_NAME, len(summaries), len(all_claims))
    return FindingsPacket(topic=topic, summaries=summaries, claims=all_claims)
