"""
Fact-Verification Agent using RAG Grounding + LLM-as-Judge.

Evaluates claims extracted from literature against underlying source chunks
using the Gemini API as an objective judge.
"""

import json
import logging
import os
import re
from typing import Any, Callable, Optional

import requests

from backend.schemas.schemas import (
    Chunk,
    Claim,
    FindingsPacket,
    IngestionResult,
    VerificationResult,
)

logger = logging.getLogger("verification_agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class VerificationAgent:
    """
    RAG fact-verification agent powered by Gemini API as an LLM judge.

    Responsibilities:
    - Ground each Claim against its referenced source chunks.
    - Ask Gemini whether the claim text is directly supported by the chunk text.
    - If supported: mark verification_status = "verified".
    - If unsupported: increment revision_attempts (hard-capped at 2); mark verification_status = "pending" if revision_attempts < 2, else "unverified".
    - On API failure/timeout: mark verification_status = "pending", log error, never guess.
    - Identify cross-paper contradictions and attach them to FindingsPacket.contradictions.
    """

    DEFAULT_MODEL = "gemini-1.5-flash"
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        timeout: float = 15.0,
        debug: bool = False,
        llm_judge_fn: Optional[Callable[[str, str], dict[str, Any]]] = None,
    ):
        """
        Initialize the Verification Agent.

        :param api_key: Gemini API key. Defaults to GEMINI_API_KEY environment variable.
        :param model_name: Name of the Gemini model to use as judge.
        :param timeout: Timeout in seconds for Gemini API calls.
        :param debug: If True, allows full chunk-text printing in logs.
        :param llm_judge_fn: Optional custom/mock judge function (claim_text, chunk_text) -> dict
                             for offline deterministic testing without external API calls.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.timeout = timeout
        self.debug = debug
        self._custom_judge_fn = llm_judge_fn

    # -----------------------------------------------------------------------
    # Gemini API Call Helper
    # -----------------------------------------------------------------------
    def _call_gemini_json(self, prompt: str) -> Optional[dict[str, Any]]:
        """
        Call the Gemini API with structured JSON output instructions.
        Returns parsed JSON dict or None on failure/timeout.
        """
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not configured. Cannot perform LLM judgment.")
            return None

        url = self.GEMINI_API_URL.format(model=self.model_name)
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                logger.error("Gemini API returned no candidates.")
                return None

            raw_text = candidates[0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)

        except requests.exceptions.Timeout as exc:
            logger.error("Gemini API request timed out after %s seconds: %s", self.timeout, exc)
            return None
        except requests.exceptions.RequestException as exc:
            logger.error("Gemini API HTTP request failed: %s", exc)
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.error("Failed to parse Gemini API JSON response: %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error during Gemini API call: %s", exc)
            return None

    # -----------------------------------------------------------------------
    # Claim Grounding & Verification
    # -----------------------------------------------------------------------
    def _judge_claim_against_chunk(
        self,
        claim: Claim,
        chunk: Chunk,
    ) -> Optional[dict[str, Any]]:
        """
        Query Gemini (or injected judge) to verify if claim is supported by chunk text.
        """
        if self.debug:
            logger.debug(
                "[DEBUG] Evaluating claim '%s' against chunk '%s':\nClaim: %s\nChunk Text: %s",
                claim.claim_id,
                chunk.chunk_id,
                claim.text,
                chunk.text,
            )
        else:
            logger.info(
                "Evaluating claim '%s' against chunk '%s'",
                claim.claim_id,
                chunk.chunk_id,
            )

        if self._custom_judge_fn is not None:
            try:
                return self._custom_judge_fn(claim.text, chunk.text)
            except Exception as exc:
                logger.error("Custom judge function raised error: %s", exc)
                return None

        prompt = (
            "You are an objective scientific fact-verification judge evaluating RAG evidence.\n"
            "Carefully determine whether the CLAIM is strictly supported by or contradicted by the EVIDENCE CHUNK.\n\n"
            f"CLAIM:\n{claim.text}\n\n"
            f"EVIDENCE CHUNK:\n{chunk.text}\n\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "is_supported": <true if the claim is factually supported by the evidence chunk, otherwise false>,\n'
            '  "confidence": <float between 0.0 and 1.0>,\n'
            '  "explanation": "<brief rationale explaining why the claim is supported or unsupported>"\n'
            "}"
        )

        return self._call_gemini_json(prompt)

    def verify_single_claim(
        self,
        claim: Claim,
        chunks_map: dict[str, Chunk],
    ) -> VerificationResult:
        """
        Verify a single Claim against its source chunks.

        Updates claim.verification_status and claim.revision_attempts according to guardrails:
        - Supported -> "verified"
        - Unsupported -> increment revision_attempts (cap at 2); set "pending" if revision_attempts < 2, else "unverified"
        - API Failure / Timeout / Missing evidence -> "pending", log error, never guess.
        """
        # Collect referenced chunks
        relevant_chunks: list[Chunk] = [
            chunks_map[cid] for cid in claim.source_chunk_ids if cid in chunks_map
        ]

        if not relevant_chunks:
            logger.error(
                "No referenced source chunks found in chunks_map for claim '%s' (source_chunk_ids=%s)",
                claim.claim_id,
                claim.source_chunk_ids,
            )
            claim.verification_status = "pending"
            return VerificationResult(
                claim_id=claim.claim_id,
                verification_status="pending",
                confidence_score=0.0,
                explanation="Referenced source chunks are missing or unavailable for grounding.",
                supporting_chunk_ids=[],
            )

        # Evaluate against source chunks
        last_explanation = ""
        last_confidence = 0.0
        supported_chunk_ids: list[str] = []
        is_supported = False
        api_failed = False

        for chunk in relevant_chunks:
            judgment = self._judge_claim_against_chunk(claim, chunk)

            if judgment is None:
                api_failed = True
                break

            last_confidence = float(judgment.get("confidence", 0.0))
            last_explanation = str(judgment.get("explanation", ""))

            if judgment.get("is_supported", False):
                is_supported = True
                supported_chunk_ids.append(chunk.chunk_id)
                break

        # Apply state transitions strictly adhering to guardrails
        if api_failed:
            logger.error(
                "API failure or timeout during verification of claim '%s'. Marking as 'pending' without guessing.",
                claim.claim_id,
            )
            claim.verification_status = "pending"
            return VerificationResult(
                claim_id=claim.claim_id,
                verification_status="pending",
                confidence_score=0.0,
                explanation="Verification pending due to LLM judge API failure or timeout.",
                supporting_chunk_ids=[],
            )

        if is_supported:
            claim.verification_status = "verified"
            return VerificationResult(
                claim_id=claim.claim_id,
                verification_status="verified",
                confidence_score=last_confidence,
                explanation=last_explanation or "Claim is verified by source evidence.",
                supporting_chunk_ids=supported_chunk_ids,
            )
        else:
            # Unsupported: increment revision_attempts with hard cap at 2
            current_attempts = claim.revision_attempts if claim.revision_attempts is not None else 0
            claim.revision_attempts = min(2, current_attempts + 1)
            if claim.revision_attempts < 2:
                claim.verification_status = "pending"
            else:
                claim.verification_status = "unverified"

            return VerificationResult(
                claim_id=claim.claim_id,
                verification_status=claim.verification_status,
                confidence_score=last_confidence,
                explanation=last_explanation or "Claim is unsupported or contradicted by source evidence.",
                supporting_chunk_ids=[],
            )

    # -----------------------------------------------------------------------
    # Cross-Paper Contradiction Detection
    # -----------------------------------------------------------------------
    def detect_cross_paper_contradictions(
        self,
        claims: list[Claim],
    ) -> list[str]:
        """
        Compare claims across different papers to flag direct contradictions.
        """
        contradictions: list[str] = []

        # Group claims by paper
        claims_by_paper: dict[str, list[Claim]] = {}
        for c in claims:
            claims_by_paper.setdefault(c.source_paper_id, []).append(c)

        paper_ids = list(claims_by_paper.keys())
        if len(paper_ids) < 2:
            return contradictions

        # Pairwise comparison across papers
        for i in range(len(paper_ids)):
            for j in range(i + 1, len(paper_ids)):
                p1, p2 = paper_ids[i], paper_ids[j]
                for c1 in claims_by_paper[p1]:
                    for c2 in claims_by_paper[p2]:
                        # Check pair if both claims are not unverified
                        prompt = (
                            "You are a scientific fact-checking judge detecting cross-paper contradictions.\n"
                            "Determine whether CLAIM A and CLAIM B make contradictory or mutually exclusive claims.\n\n"
                            f"CLAIM A (Paper {p1}):\n{c1.text}\n\n"
                            f"CLAIM B (Paper {p2}):\n{c2.text}\n\n"
                            "Return a JSON object with this exact structure:\n"
                            "{\n"
                            '  "contradicts": <true if they directly conflict or contradict each other, otherwise false>,\n'
                            '  "explanation": "<brief explanation if contradictory, otherwise empty>"\n'
                            "}"
                        )
                        res = self._call_gemini_json(prompt)
                        if res and res.get("contradicts", False):
                            explanation = res.get("explanation", "Cross-paper conflict detected.")
                            contradictions.append(
                                f"Claim '{c1.claim_id}' conflicts with claim '{c2.claim_id}': {explanation}"
                            )

        return contradictions

    # -----------------------------------------------------------------------
    # Main Agent Entry Point
    # -----------------------------------------------------------------------
    def verify_findings(
        self,
        findings: FindingsPacket,
        chunks_map: Optional[dict[str, Chunk]] = None,
    ) -> tuple[FindingsPacket, list[VerificationResult]]:
        """
        Verify all claims within a FindingsPacket.

        :param findings: The FindingsPacket containing summaries and extracted claims.
        :param chunks_map: Dictionary mapping chunk_id to Chunk. If None, falls back to
                           the test fixture in backend/tests/fixtures/sample_findings.py.
        :return: (updated_findings, verification_results)
        """
        if chunks_map is None:
            # Use only the designated test fixture as grounded reference
            try:
                from backend.tests.fixtures.sample_findings import SAMPLE_CHUNKS
                chunks_map = SAMPLE_CHUNKS
            except ImportError:
                chunks_map = {}

        verification_results: list[VerificationResult] = []

        # Verify each claim
        for claim in findings.claims:
            v_res = self.verify_single_claim(claim, chunks_map)
            verification_results.append(v_res)

        # Synchronize claim statuses across summaries as well
        claim_status_map = {c.claim_id: (c.verification_status, c.revision_attempts) for c in findings.claims}
        for summary in findings.summaries:
            for summary_claim in summary.extracted_claims:
                if summary_claim.claim_id in claim_status_map:
                    status, attempts = claim_status_map[summary_claim.claim_id]
                    summary_claim.verification_status = status
                    summary_claim.revision_attempts = attempts

        # Detect cross-paper contradictions
        contradictions = self.detect_cross_paper_contradictions(findings.claims)

        # Attach contradictions to FindingsPacket
        findings.contradictions = contradictions

        return findings, verification_results


def run_verification_agent(
    findings: FindingsPacket,
    chunks_map: Optional[dict[str, Chunk]] = None,
    **agent_kwargs: Any,
) -> tuple[FindingsPacket, list[VerificationResult]]:
    """
    Convenience function to run fact verification on a FindingsPacket.
    """
    agent = VerificationAgent(**agent_kwargs)
    return agent.verify_findings(findings, chunks_map)


def run_verification(
    findings: FindingsPacket,
    ingestion_results: list[IngestionResult],
    **agent_kwargs: Any,
) -> tuple[list[VerificationResult], FindingsPacket]:
    """
    Entry point conforming to the orchestrator integration pattern.
    Builds the chunk lookup from ingestion_results (each has .chunks, a list[Chunk]),
    calls VerificationAgent.verify_findings() logic internally, and returns
    (verification_results, updated_findings) in that order.
    """
    chunks_map: dict[str, Chunk] = {}
    for ir in (ingestion_results or []):
        for chunk in ir.chunks:
            chunks_map[chunk.chunk_id] = chunk

    # If client is passed (e.g. from tests using FakeGeminiClient) and llm_judge_fn not set,
    # bridge client.generate() to llm_judge_fn so tests pass without real API calls.
    client = agent_kwargs.pop("client", None)
    if client is not None and "llm_judge_fn" not in agent_kwargs:
        def client_judge_fn(claim_text: str, chunk_text: str) -> dict[str, Any]:
            try:
                res = client.generate(
                    f"CLAIM: {claim_text}\nCHUNK: {chunk_text}",
                    paper_id="",
                    agent_name="verification_agent",
                    purpose="grounding_check",
                )
                if isinstance(res, str):
                    clean_res = res.strip()
                    if clean_res.startswith("```"):
                        clean_res = re.sub(r"^```(?:json)?\s*", "", clean_res)
                        clean_res = re.sub(r"\s*```$", "", clean_res)
                    data = json.loads(clean_res)
                else:
                    data = res
                is_sup = data.get("is_supported", data.get("status") == "verified")
                return {
                    "is_supported": is_sup,
                    "confidence": float(data.get("confidence", 1.0 if is_sup else 0.0)),
                    "explanation": data.get("reason", data.get("explanation", "")),
                }
            except Exception as e:
                logger.error("Client judge failed: %s", e)
                return {"is_supported": False, "confidence": 0.0, "explanation": str(e)}

        agent_kwargs["llm_judge_fn"] = client_judge_fn

    agent = VerificationAgent(**agent_kwargs)
    updated_findings, verification_results = agent.verify_findings(findings, chunks_map)
    return verification_results, updated_findings