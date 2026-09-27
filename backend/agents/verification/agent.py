"""
Verification Agent (Person B) - the most accuracy-critical component in the
system; this is what the project's accuracy grade will largely be judged on.

For every claim from the Summarization Agent:
  1. RAG-grounding check: does the claim actually trace to the retrieved
     chunk text? (LLM-as-judge via Gemini - framed as a best-effort
     grounding check, not a fact-truth oracle.)
  2. If unsupported, send it back to the Summarization Agent for revision -
     capped at 2 revision loops (Claim.revision_attempts). After 2 failed
     attempts, mark "unverified" rather than looping forever.
  3. Flag contradictions across different papers' claims - never silently
     pick one side.

Never invents new claims - only checks, revises the text of, and flags
existing claims produced by the Summarization Agent.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from backend.agents.common.llm_client import GeminiClient
from backend.agents.summarization.agent import revise_claim
from backend.schemas.schemas import Claim, FindingsPacket, IngestionResult, VerificationResult

logger = logging.getLogger("research_assistant.verification")

AGENT_NAME = "verification_agent"
MAX_REVISION_LOOPS = 2  # hard rule - both for token budget and to avoid an infinite pipeline hang


def _build_chunk_lookup(ingestion_results: List[IngestionResult]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for result in ingestion_results:
        for chunk in result.chunks:
            lookup[chunk.chunk_id] = chunk.text
    return lookup


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else "{}"


def _grounding_check(client: GeminiClient, claim: Claim, chunk_text: str) -> Tuple[str, float, str]:
    """
    LLM-as-judge grounding check. Returns (status, confidence, explanation).
    status is one of: "verified", "unsupported". Logged so it's defensible
    in the viva.
    """
    prompt = f"""You are a strict fact-checker. Determine whether the CLAIM below is
directly and specifically supported by the SOURCE TEXT. Do not use outside
knowledge - judge only on the source text given.

CLAIM: {claim.text}

SOURCE TEXT: {chunk_text}

Respond as JSON only, in exactly this shape:
{{"status": "verified" or "unsupported", "confidence": <0.0-1.0>, "reason": "<one sentence>"}}
"""
    raw = client.generate(prompt, paper_id=claim.source_paper_id, agent_name=AGENT_NAME, purpose="grounding_check")

    try:
        data = json.loads(_extract_json(raw))
        status = data.get("status", "unsupported")
        if status not in ("verified", "unsupported"):
            status = "unsupported"
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))
        return status, confidence, reason
    except Exception:
        logger.warning("[%s] Could not parse judge response for claim=%s, treating as unsupported", AGENT_NAME, claim.claim_id)
        return "unsupported", 0.0, "Judge response could not be parsed."


def _verify_claim_with_revision_loop(
    client: GeminiClient, claim: Claim, chunk_lookup: Dict[str, str]
) -> Tuple[Claim, VerificationResult]:
    supporting_chunk_ids = [cid for cid in claim.source_chunk_ids if cid in chunk_lookup]

    if not supporting_chunk_ids:
        result = VerificationResult(
            claim_id=claim.claim_id,
            verification_status="unsupported",
            confidence_score=0.0,
            explanation="No supporting source chunk was found for this claim.",
            supporting_chunk_ids=[],
        )
        return claim.model_copy(update={"verification_status": "unsupported"}), result

    chunk_text = "\n".join(chunk_lookup[cid] for cid in supporting_chunk_ids)
    working_claim = claim
    status, confidence, reason = "unsupported", 0.0, ""

    for attempt in range(MAX_REVISION_LOOPS + 1):
        status, confidence, reason = _grounding_check(client, working_claim, chunk_text)
        logger.info(
            "[%s] claim=%s attempt=%d status=%s confidence=%.2f reason=%s",
            AGENT_NAME, working_claim.claim_id, attempt, status, confidence, reason,
        )

        if status == "verified":
            result = VerificationResult(
                claim_id=claim.claim_id,
                verification_status="verified",
                confidence_score=confidence,
                explanation=reason,
                supporting_chunk_ids=supporting_chunk_ids,
            )
            final_claim = working_claim.model_copy(update={"verification_status": "verified", "revision_attempts": attempt})
            return final_claim, result

        if attempt == MAX_REVISION_LOOPS:
            break  # hard cap reached - fall through to "unverified"

        # Send back to the Summarization Agent for a bounded revision.
        working_claim = revise_claim(client, working_claim, chunk_text, reason)
        working_claim = working_claim.model_copy(update={"revision_attempts": attempt + 1})

    result = VerificationResult(
        claim_id=claim.claim_id,
        verification_status="unverified",
        confidence_score=confidence,
        explanation=f"Unsupported after {MAX_REVISION_LOOPS} revision attempts. Last judge reason: {reason}",
        supporting_chunk_ids=supporting_chunk_ids,
    )
    final_claim = working_claim.model_copy(update={"verification_status": "unverified", "revision_attempts": MAX_REVISION_LOOPS})
    return final_claim, result


def _check_contradictions(client: GeminiClient, claims: List[Claim], results: List[VerificationResult]) -> None:
    """
    Compare claims across different papers and flag contradictions.
    Mutates `results` in place: sets verification_status="contradicted" on
    BOTH sides of a detected contradiction rather than silently picking one.
    No dedicated contradiction-pair field exists in the locked
    VerificationResult schema, so the conflicting claim_id is recorded in
    `explanation` instead - see ASSUMPTIONS.md #3.
    """
    checkable = [c for c in claims if c.verification_status in ("verified", "unverified")]
    result_by_claim_id = {r.claim_id: r for r in results}

    for i in range(len(checkable)):
        for j in range(i + 1, len(checkable)):
            a, b = checkable[i], checkable[j]
            if a.source_paper_id == b.source_paper_id:
                continue  # contradiction check is across different papers only

            prompt = f"""Do these two claims, from different papers, directly contradict
each other (i.e. they cannot both be true)? Answer with only "YES" or "NO".

Claim A ({a.source_paper_id}): {a.text}
Claim B ({b.source_paper_id}): {b.text}
"""
            answer = client.generate(
                prompt, paper_id="__contradiction_check__", agent_name=AGENT_NAME, purpose="contradiction_check"
            ).strip().upper()

            if answer.startswith("YES"):
                logger.warning("[%s] Contradiction flagged between %s and %s", AGENT_NAME, a.claim_id, b.claim_id)
                for claim_id, other_id in ((a.claim_id, b.claim_id), (b.claim_id, a.claim_id)):
                    r = result_by_claim_id.get(claim_id)
                    if r:
                        r.verification_status = "contradicted"
                        r.explanation = (
                            f"{r.explanation} | Contradicts claim {other_id} from a different "
                            "paper - not auto-resolved, flagged for review."
                        ).strip(" |")


def run_verification(
    findings: FindingsPacket,
    ingestion_results: List[IngestionResult],
    client: Optional[GeminiClient] = None,
) -> Tuple[List[VerificationResult], FindingsPacket]:
    """
    Entry point called from graph.py's verification_agent node.
    Returns (verification_results, updated_findings) - updated_findings
    carries revised claim text / revision_attempts / verification_status
    back onto the SAME Claim objects (never adds new claims).
    """
    client = client or GeminiClient()

    if not findings or not findings.claims:
        logger.info("[%s] No claims to verify.", AGENT_NAME)
        return [], findings

    if not ingestion_results:
        logger.info("[%s] No ingestion results available - cannot ground claims.", AGENT_NAME)
        return [], findings

    chunk_lookup = _build_chunk_lookup(ingestion_results)

    updated_claims: List[Claim] = []
    results: List[VerificationResult] = []

    for claim in findings.claims:
        try:
            final_claim, result = _verify_claim_with_revision_loop(client, claim, chunk_lookup)
        except Exception:
            logger.exception("[%s] Verification failed for claim=%s - failing gracefully", AGENT_NAME, claim.claim_id)
            final_claim = claim.model_copy(update={"verification_status": "unverified"})
            result = VerificationResult(
                claim_id=claim.claim_id,
                verification_status="unverified",
                confidence_score=0.0,
                explanation="Verification agent encountered an internal error.",
                supporting_chunk_ids=[],
            )
        updated_claims.append(final_claim)
        results.append(result)

    try:
        _check_contradictions(client, updated_claims, results)
    except Exception:
        logger.exception("[%s] Contradiction check failed - continuing without it.", AGENT_NAME)

    updated_findings = findings.model_copy(update={"claims": updated_claims})

    logger.info("[%s] %d claims verified.", AGENT_NAME, len(results))
    return results, updated_findings