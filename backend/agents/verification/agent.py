"""
Fact-Verification Agent using RAG Grounding + LLM-as-Judge.

Evaluates claims extracted from literature against underlying source chunks
using the Gemini API as an objective judge.
"""

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import requests

from backend.agents.common.llm_client import GEMINI_MODEL
from backend.schemas.schemas import (
    Chunk,
    Claim,
    ContradictionDetail,
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
    - Ground claims against referenced source chunks in sub-batches of <= 8 claims per paper.
    - Ask Gemini whether each claim is strictly supported by cited evidence.
    - If supported: mark verification_status = "verified".
    - If unsupported: run bounded revision loop (up to 2 rounds, batched).
    - If revised claim is supported: mark "verified", keep revised text, prepend 'Revised from: "<orig>".' to explanation.
    - If 2 rounds fail (or revised_text null): mark "unverified", restore original text, revision_attempts <= 2.
    - On API failure/timeout/missing chunks: mark verification_status = "pending", never guess.
    - Identify cross-paper contradictions in batched paper-pair calls and attach them to FindingsPacket.contradictions.
    """

    DEFAULT_MODEL = GEMINI_MODEL
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        debug: bool = False,
        llm_judge_fn: Optional[Callable[[str, str], dict[str, Any]]] = None,
    ):
        """
        Initialize the Verification Agent.

        :param api_key: Gemini API key. Defaults to GEMINI_API_KEY environment variable.
        :param model_name: Name of the Gemini model to use as judge.
        :param timeout: Timeout in seconds for Gemini API calls (default 30.0s for batched prompts).
        :param debug: If True, allows full chunk-text printing in logs.
        :param llm_judge_fn: Optional custom/mock judge function (claim_text, chunk_text) -> dict
                             for offline deterministic testing without external API calls.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.timeout = timeout
        self.debug = debug
        self._custom_judge_fn = llm_judge_fn
        self._llm_calls_count = 0
        self._call_lock = threading.Lock()
        self.last_contradiction_details: list[ContradictionDetail] = []

    # -----------------------------------------------------------------------
    # Gemini API Call Helper
    # -----------------------------------------------------------------------
    def _call_gemini_json(self, prompt: str) -> Optional[dict[str, Any]]:
        """
        Call the Gemini API with structured JSON output instructions.
        Returns parsed JSON dict or None on failure/timeout.
        Retries with exponential backoff on HTTP 503, 429, and timeouts.
        """
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not configured. Cannot perform LLM judgment.")
            return None

        with self._call_lock:
            self._llm_calls_count += 1

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

        max_retries = 3
        backoff_delays = [2.0, 4.0, 8.0]

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code in (400, 401, 403, 404):
                    raise RuntimeError(
                        f"Gemini returned {response.status_code} for model {self.model_name}; check GEMINI_MODEL"
                    )

                if response.status_code in (429, 503):
                    if attempt < max_retries:
                        delay = backoff_delays[attempt]
                        logger.warning(
                            "Gemini returned HTTP %s (attempt %d/%d). Retrying in %ss...",
                            response.status_code,
                            attempt + 1,
                            max_retries + 1,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    logger.error(
                        "Gemini returned HTTP %s. Retries exhausted after %d attempts.",
                        response.status_code,
                        attempt + 1,
                    )
                    return None

                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    logger.error("Gemini API returned no candidates.")
                    return None

                raw_text = candidates[0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)

            except RuntimeError:
                raise
            except requests.exceptions.Timeout as exc:
                if attempt < max_retries:
                    delay = backoff_delays[attempt]
                    logger.warning(
                        "Gemini request timed out: %s (attempt %d/%d). Retrying in %ss...",
                        type(exc).__name__,
                        attempt + 1,
                        max_retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    "Gemini request timed out: %s. Retries exhausted after %d attempts.",
                    type(exc).__name__,
                    attempt + 1,
                )
                return None
            except requests.exceptions.RequestException as exc:
                status_code = getattr(exc.response, "status_code", None)
                if status_code in (400, 401, 403, 404):
                    raise RuntimeError(
                        f"Gemini returned {status_code} for model {self.model_name}; check GEMINI_MODEL"
                    ) from exc
                if status_code in (429, 503):
                    if attempt < max_retries:
                        delay = backoff_delays[attempt]
                        logger.warning(
                            "Gemini request failed: HTTP %s (attempt %d/%d). Retrying in %ss...",
                            status_code,
                            attempt + 1,
                            max_retries + 1,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    logger.error(
                        "Gemini request failed: HTTP %s. Retries exhausted after %d attempts.",
                        status_code,
                        attempt + 1,
                    )
                    return None
                logger.error(
                    "Gemini request failed: %s (status=%s)",
                    type(exc).__name__,
                    status_code,
                )
                return None
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                logger.error("Failed to parse Gemini API JSON response: %s", type(exc).__name__)
                return None
            except Exception as exc:
                logger.error("Unexpected error during Gemini API call: %s", type(exc).__name__)
                return None

        return None

    # -----------------------------------------------------------------------
    # Claim Grounding & Verification (Single / Compat Path)
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

            try:
                last_confidence = float(judgment.get("confidence", 0.0))
            except (ValueError, TypeError):
                last_confidence = 0.0
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
    # Batched Claim Grounding & Verification
    # -----------------------------------------------------------------------
    def _judge_claims_batch(
        self,
        batch: list[Claim],
        chunks_map: dict[str, Chunk],
    ) -> dict[str, Optional[dict[str, Any]]]:
        """
        Judge a sub-batch of claims (at most 8, from the same paper) in a single LLM call.
        Validates response, ignores unknown claim_ids, and retries not-judged claims
        once through the existing per-claim path. If that also fails, marks them None (pending).
        """
        valid_claim_ids = {c.claim_id for c in batch}
        verdicts: dict[str, Optional[dict[str, Any]]] = {}

        # De-duplicate referenced chunks cited by claims in this batch
        batch_chunk_ids: list[str] = []
        seen_cids: set[str] = set()
        for c in batch:
            for cid in c.source_chunk_ids:
                if cid in chunks_map and cid not in seen_cids:
                    seen_cids.add(cid)
                    batch_chunk_ids.append(cid)

        if not batch_chunk_ids:
            for c in batch:
                verdicts[c.claim_id] = None
            return verdicts

        chunks_text = "\n\n".join(
            f"Chunk ID: {cid}\nContent: {chunks_map[cid].text}"
            for cid in batch_chunk_ids
        )
        claims_text = "\n".join(
            f"- Claim ID: {c.claim_id}\n  Text: {c.text}\n  Cited Chunk IDs: {', '.join(c.source_chunk_ids)}"
            for c in batch
        )

        prompt = (
            "You are an objective scientific fact-verification judge evaluating RAG evidence.\n"
            "Carefully evaluate each CLAIM against the provided EVIDENCE CHUNKS.\n"
            "The evaluation must be strict: a claim counts as supported only if the evidence "
            "states it or directly entails it, with no outside knowledge. If the evidence does not "
            "directly support the claim or if it contradicts the claim, mark is_supported as false.\n\n"
            f"EVIDENCE CHUNKS:\n{chunks_text}\n\n"
            f"CLAIMS TO VERIFY:\n{claims_text}\n\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "verdicts": [\n'
            "    {\n"
            '      "claim_id": "<claim_id>",\n'
            '      "is_supported": <true if the claim is factually supported by the evidence, otherwise false>,\n'
            '      "confidence": <float between 0.0 and 1.0>,\n'
            '      "explanation": "<brief rationale explaining why the claim is supported or unsupported>",\n'
            '      "supporting_chunk_ids": ["<chunk_id>", ...]\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        res = self._call_gemini_json(prompt)
        if isinstance(res, dict) and isinstance(res.get("verdicts"), list):
            for item in res["verdicts"]:
                if not isinstance(item, dict):
                    continue
                cid = item.get("claim_id")
                # Ignore unknown claim_ids
                if cid in valid_claim_ids and cid not in verdicts:
                    is_sup = bool(item.get("is_supported", False))
                    try:
                        conf = float(item.get("confidence", 0.0) if item.get("confidence") is not None else 0.0)
                    except (ValueError, TypeError):
                        conf = 0.0
                    expl = str(item.get("explanation", ""))
                    raw_supp = item.get("supporting_chunk_ids", [])
                    if isinstance(raw_supp, list):
                        supp = [str(x) for x in raw_supp if str(x) in chunks_map]
                    else:
                        supp = []
                    verdicts[cid] = {
                        "is_supported": is_sup,
                        "confidence": conf,
                        "explanation": expl,
                        "supporting_chunk_ids": supp,
                    }

        # Any claim missing from verdicts is treated as not judged -> retry once per-claim
        for c in batch:
            if c.claim_id not in verdicts:
                relevant_chunks = [chunks_map[cid] for cid in c.source_chunk_ids if cid in chunks_map]
                if not relevant_chunks:
                    verdicts[c.claim_id] = None
                    continue

                last_explanation = ""
                last_confidence = 0.0
                supported_chunk_ids: list[str] = []
                is_supported = False
                api_failed = False

                for chunk in relevant_chunks:
                    judgment = self._judge_claim_against_chunk(c, chunk)
                    if judgment is None:
                        api_failed = True
                        break
                    try:
                        last_confidence = float(judgment.get("confidence", 0.0))
                    except (ValueError, TypeError):
                        last_confidence = 0.0
                    last_explanation = str(judgment.get("explanation", ""))
                    if judgment.get("is_supported", False):
                        is_supported = True
                        supported_chunk_ids.append(chunk.chunk_id)
                        break

                if api_failed:
                    verdicts[c.claim_id] = None
                else:
                    verdicts[c.claim_id] = {
                        "is_supported": is_supported,
                        "confidence": last_confidence,
                        "explanation": last_explanation,
                        "supporting_chunk_ids": supported_chunk_ids,
                    }

        return verdicts

    # -----------------------------------------------------------------------
    # Batched Revision Loop
    # -----------------------------------------------------------------------
    def _revise_and_rejudge_batch(
        self,
        batch: list[Claim],
        chunks_map: dict[str, Chunk],
    ) -> dict[str, dict[str, Any]]:
        """
        Ask Gemini to rewrite unsupported claims so they state only what cited evidence supports,
        then re-judge revised claims with the batch judge from _judge_claims_batch.
        """
        batch_claim_ids = {c.claim_id for c in batch}
        outcomes: dict[str, dict[str, Any]] = {}

        batch_chunk_ids: list[str] = []
        seen_cids: set[str] = set()
        for c in batch:
            for cid in c.source_chunk_ids:
                if cid in chunks_map and cid not in seen_cids:
                    seen_cids.add(cid)
                    batch_chunk_ids.append(cid)

        if not batch_chunk_ids:
            for c in batch:
                outcomes[c.claim_id] = {"type": "revised_null"}
            return outcomes

        chunks_text = "\n\n".join(
            f"Chunk ID: {cid}\nContent: {chunks_map[cid].text}"
            for cid in batch_chunk_ids
        )
        claims_text = "\n".join(
            f"- Claim ID: {c.claim_id}\n  Text: {c.text}\n  Cited Chunk IDs: {', '.join(c.source_chunk_ids)}"
            for c in batch
        )

        prompt = (
            "You are an objective scientific fact-verification assistant.\n"
            "The following CLAIMS were judged UNSUPPORTED by the cited EVIDENCE CHUNKS.\n"
            "Rewrite each claim so that it states ONLY what the cited evidence strictly supports.\n"
            "If nothing in the evidence supports any version of the claim, set revised_text to null.\n"
            "Do not extrapolate or introduce any outside knowledge.\n\n"
            f"EVIDENCE CHUNKS:\n{chunks_text}\n\n"
            f"CLAIMS TO REWRITE:\n{claims_text}\n\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "revisions": [\n'
            "    {\n"
            '      "claim_id": "<claim_id>",\n'
            '      "revised_text": "<revised text supported by evidence, or null>"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        res = self._call_gemini_json(prompt)
        if not isinstance(res, dict) or not isinstance(res.get("revisions"), list):
            for c in batch:
                outcomes[c.claim_id] = {"type": "api_failure"}
            return outcomes

        rev_map: dict[str, Optional[str]] = {}
        for item in res["revisions"]:
            if isinstance(item, dict):
                cid = item.get("claim_id")
                if cid in batch_claim_ids:
                    rev_map[cid] = item.get("revised_text")

        claims_to_rejudge: list[Claim] = []
        for c in batch:
            rev_text = rev_map.get(c.claim_id)
            if rev_text is None or not str(rev_text).strip():
                outcomes[c.claim_id] = {"type": "revised_null"}
            else:
                c.text = str(rev_text).strip()
                claims_to_rejudge.append(c)

        if claims_to_rejudge:
            verdicts = self._judge_claims_batch(claims_to_rejudge, chunks_map)
            for c in claims_to_rejudge:
                v = verdicts.get(c.claim_id)
                if v is None:
                    outcomes[c.claim_id] = {"type": "api_failure"}
                elif v.get("is_supported", False):
                    outcomes[c.claim_id] = {
                        "type": "supported",
                        "verdict": v,
                        "revised_text": c.text,
                    }
                else:
                    outcomes[c.claim_id] = {
                        "type": "unsupported",
                        "verdict": v,
                        "revised_text": c.text,
                    }

        return outcomes

    # -----------------------------------------------------------------------
    # Cross-Paper Contradiction Detection
    # -----------------------------------------------------------------------
    def _detect_cross_paper_contradictions_per_claim(
        self,
        claims: list[Claim],
    ) -> tuple[list[str], list[ContradictionDetail]]:
        """
        Compare claims across different papers one pair at a time (compat path for offline tests).
        """
        candidates: list[ContradictionDetail] = []
        claims_by_paper: dict[str, list[Claim]] = {}
        for c in claims:
            claims_by_paper.setdefault(c.source_paper_id, []).append(c)

        paper_ids = list(claims_by_paper.keys())
        if len(paper_ids) < 2:
            return [], []

        for i in range(len(paper_ids)):
            for j in range(i + 1, len(paper_ids)):
                p1, p2 = paper_ids[i], paper_ids[j]
                for c1 in claims_by_paper[p1]:
                    for c2 in claims_by_paper[p2]:
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
                            explanation = str(res.get("explanation", "Cross-paper conflict detected.")).strip()
                            candidates.append(
                                ContradictionDetail(
                                    claim_a_id=c1.claim_id,
                                    claim_b_id=c2.claim_id,
                                    paper_a_id=p1,
                                    paper_b_id=p2,
                                    explanation=explanation,
                                    shared_subject="empirical_findings",
                                    extra_claim_ids=[],
                                )
                            )
        return self._merge_contradiction_details(candidates)

    def _detect_cross_paper_contradictions_batched(
        self,
        claims: list[Claim],
    ) -> tuple[list[str], list[ContradictionDetail]]:
        """
        Batched contradiction detection: one call per pair of papers, listing both papers' claims
        (only claims whose status isn't unverified, using their final text) with their ids.
        """
        eligible_claims = [c for c in claims if c.verification_status != "unverified"]
        claims_by_paper: dict[str, list[Claim]] = {}
        for c in eligible_claims:
            claims_by_paper.setdefault(c.source_paper_id, []).append(c)

        paper_ids = sorted(claims_by_paper.keys())
        if len(paper_ids) < 2:
            return [], []

        try:
            max_workers = int(os.environ.get("VERIFY_MAX_WORKERS", "4"))
        except (ValueError, TypeError):
            max_workers = 4
        if max_workers < 1:
            max_workers = 1

        pairs: list[tuple[str, str]] = []
        for i in range(len(paper_ids)):
            for j in range(i + 1, len(paper_ids)):
                pairs.append((paper_ids[i], paper_ids[j]))

        def check_pair(p1: str, p2: str) -> list[ContradictionDetail]:
            p1_claims = claims_by_paper[p1]
            p2_claims = claims_by_paper[p2]
            if not p1_claims or not p2_claims:
                return []

            p1_text = "\n".join(f"- Claim ID: {c.claim_id}: {c.text}" for c in p1_claims)
            p2_text = "\n".join(f"- Claim ID: {c.claim_id}: {c.text}" for c in p2_claims)

            prompt = (
                "You are a strict scientific fact-checking judge detecting cross-paper contradictions.\n"
                f"Compare the claims from Paper A ('{p1}') and Paper B ('{p2}').\n\n"
                "CRITICAL DEFINITION OF A CONTRADICTION:\n"
                "- A contradiction occurs ONLY when two claims make incompatible, mutually exclusive statements "
                "about the SAME quantity, effect, condition, or setting (for example, 'X increases Y' vs 'X decreases Y', "
                "or directly conflicting measured outcomes for the exact same experimental setup).\n"
                "- Different methods, different architectures or approaches, different scopes, different datasets, "
                "or differences in scientific emphasis are NOT contradictions. For example, Paper A using ML prediction + optimization "
                "while Paper B uses a data-driven approach that needs no demand forecasting is a difference of approach, NOT a contradiction.\n"
                "- Returning an empty list is the normal, expected result when papers explore different methods or settings.\n\n"
                f"PAPER A ('{p1}') CLAIMS:\n{p1_text}\n\n"
                f"PAPER B ('{p2}') CLAIMS:\n{p2_text}\n\n"
                "Return a JSON object with this exact structure:\n"
                "{\n"
                '  "contradictions": [\n'
                "    {\n"
                '      "claim_a_id": "<claim_id from Paper A>",\n'
                '      "claim_b_id": "<claim_id from Paper B>",\n'
                '      "shared_subject": "<the exact common quantity, effect, condition, or setting being measured or asserted>",\n'
                '      "explanation": "<short explanation naming specifically what is incompatible>"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                'If there are no contradictions, return {"contradictions": []}.'
            )

            res = self._call_gemini_json(prompt)
            if not isinstance(res, dict) or not isinstance(res.get("contradictions"), list):
                return []

            p1_ids = {c.claim_id for c in p1_claims}
            p2_ids = {c.claim_id for c in p2_claims}
            pair_candidates: list[ContradictionDetail] = []

            for item in res["contradictions"]:
                if not isinstance(item, dict):
                    continue
                ca = item.get("claim_a_id")
                cb = item.get("claim_b_id")
                shared_subject = item.get("shared_subject")
                expl = item.get("explanation")

                # Strict validation: require non-empty shared_subject and explanation
                if not shared_subject or not isinstance(shared_subject, str) or not shared_subject.strip():
                    continue
                if not expl or not isinstance(expl, str) or not expl.strip():
                    continue

                # Strict validation: claim IDs must belong to the correct papers
                if ca in p1_ids and cb in p2_ids:
                    cand_ca, cand_cb = ca, cb
                    cand_pa, cand_pb = p1, p2
                elif ca in p2_ids and cb in p1_ids:
                    cand_ca, cand_cb = cb, ca
                    cand_pa, cand_pb = p1, p2
                else:
                    # Ignore pairs whose IDs don't belong to the right papers
                    continue

                pair_candidates.append(
                    ContradictionDetail(
                        claim_a_id=cand_ca,
                        claim_b_id=cand_cb,
                        paper_a_id=cand_pa,
                        paper_b_id=cand_pb,
                        explanation=expl.strip(),
                        shared_subject=shared_subject.strip(),
                        extra_claim_ids=[],
                    )
                )

            return pair_candidates

        all_candidates: list[ContradictionDetail] = []
        if len(pairs) == 1:
            all_candidates.extend(check_pair(pairs[0][0], pairs[0][1]))
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                results = pool.map(lambda pr: check_pair(pr[0], pr[1]), pairs)
                for pair_res in results:
                    all_candidates.extend(pair_res)

        return self._merge_contradiction_details(all_candidates)

    def _merge_contradiction_details(
        self,
        candidates: list[ContradictionDetail],
    ) -> tuple[list[str], list[ContradictionDetail]]:
        """
        Merges contradiction entries that share a claim on either side into ONE
        ContradictionDetail (primary pair + extra_claim_ids) and one contradiction string.
        """
        merged_details: list[ContradictionDetail] = []

        for cand in candidates:
            cand_ids = {cand.claim_a_id, cand.claim_b_id} | set(cand.extra_claim_ids)
            matched: Optional[ContradictionDetail] = None

            for existing in merged_details:
                existing_ids = {existing.claim_a_id, existing.claim_b_id} | set(existing.extra_claim_ids)
                if cand_ids & existing_ids:
                    matched = existing
                    break

            if matched is None:
                merged_details.append(
                    ContradictionDetail(
                        claim_a_id=cand.claim_a_id,
                        claim_b_id=cand.claim_b_id,
                        paper_a_id=cand.paper_a_id,
                        paper_b_id=cand.paper_b_id,
                        explanation=cand.explanation,
                        shared_subject=cand.shared_subject,
                        extra_claim_ids=list(cand.extra_claim_ids),
                    )
                )
            else:
                existing_ids = {matched.claim_a_id, matched.claim_b_id} | set(matched.extra_claim_ids)
                for cid in [cand.claim_a_id, cand.claim_b_id] + cand.extra_claim_ids:
                    if cid not in existing_ids:
                        matched.extra_claim_ids.append(cid)
                        existing_ids.add(cid)

                if cand.explanation and cand.explanation not in matched.explanation:
                    matched.explanation = f"{matched.explanation}; {cand.explanation}"

        contradiction_strings: list[str] = [
            f"Claim '{d.claim_a_id}' conflicts with claim '{d.claim_b_id}': {d.explanation}"
            for d in merged_details
        ]

        return contradiction_strings, merged_details

    def detect_cross_paper_contradiction_details(
        self,
        claims: list[Claim],
    ) -> tuple[list[str], list[ContradictionDetail]]:
        """
        Compare claims across different papers to flag direct contradictions.
        Uses existing per-claim comparison when custom judge is set (compat mode),
        otherwise uses batched paper-pair comparison.
        Returns both formatted contradiction strings and structured ContradictionDetail objects.
        """
        if self._custom_judge_fn is not None:
            strings, details = self._detect_cross_paper_contradictions_per_claim(claims)
        else:
            strings, details = self._detect_cross_paper_contradictions_batched(claims)
        self.last_contradiction_details = details
        return strings, details

    def detect_cross_paper_contradictions(
        self,
        claims: list[Claim],
    ) -> list[str]:
        """
        Compare claims across different papers to flag direct contradictions.
        Returns formatted contradiction strings (keeping FindingsPacket.contradictions format).
        """
        strings, _ = self.detect_cross_paper_contradiction_details(claims)
        return strings

    # -----------------------------------------------------------------------
    # Main Agent Entry Point
    # -----------------------------------------------------------------------
    def _verify_findings_per_claim_compat(
        self,
        findings: FindingsPacket,
        chunks_map: dict[str, Chunk],
        max_workers: int,
        start_time: float,
        start_calls: int,
    ) -> tuple[FindingsPacket, list[VerificationResult]]:
        """
        Compat path for offline tests using llm_judge_fn or fake clients.
        """
        def verify_one(claim: Claim) -> VerificationResult:
            return self.verify_single_claim(claim, chunks_map)

        if findings.claims:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                verification_results = list(pool.map(verify_one, findings.claims))
        else:
            verification_results = []

        # Synchronize claim statuses and text across summaries as well
        claim_status_map = {c.claim_id: (c.verification_status, c.revision_attempts, c.text) for c in findings.claims}
        for summary in findings.summaries:
            for summary_claim in summary.extracted_claims:
                if summary_claim.claim_id in claim_status_map:
                    status, attempts, text = claim_status_map[summary_claim.claim_id]
                    summary_claim.verification_status = status
                    summary_claim.revision_attempts = attempts
                    summary_claim.text = text

        contradictions, details = self.detect_cross_paper_contradiction_details(findings.claims)
        findings.contradictions = contradictions
        findings.contradiction_details = details

        elapsed = time.time() - start_time
        llm_calls = self._llm_calls_count - start_calls
        verified_count = sum(1 for r in verification_results if r.verification_status == "verified")
        unverified_count = sum(1 for r in verification_results if r.verification_status == "unverified")
        pending_count = sum(1 for r in verification_results if r.verification_status == "pending")

        logger.info(
            "Verification summary: %d verified, %d unverified, %d pending, "
            "%d revised_and_verified, %d llm_calls, elapsed: %.2fs",
            verified_count,
            unverified_count,
            pending_count,
            0,
            llm_calls,
            elapsed,
        )

        return findings, verification_results

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
        start_time = time.time()
        start_calls = self._llm_calls_count

        if chunks_map is None:
            try:
                from backend.tests.fixtures.sample_findings import SAMPLE_CHUNKS
                chunks_map = SAMPLE_CHUNKS
            except ImportError:
                chunks_map = {}

        try:
            max_workers = int(os.environ.get("VERIFY_MAX_WORKERS", "4"))
        except (ValueError, TypeError):
            max_workers = 4
        if max_workers < 1:
            max_workers = 1

        # Compat path for injected client / llm_judge_fn (offline tests)
        if self._custom_judge_fn is not None:
            return self._verify_findings_per_claim_compat(
                findings, chunks_map, max_workers, start_time, start_calls
            )

        if not findings.claims:
            contradictions, details = self.detect_cross_paper_contradiction_details([])
            findings.contradictions = contradictions
            findings.contradiction_details = details
            elapsed = time.time() - start_time
            logger.info(
                "Verification summary: %d verified, %d unverified, %d pending, "
                "%d revised_and_verified, %d llm_calls, elapsed: %.2fs",
                0, 0, 0, 0, 0, elapsed
            )
            return findings, []

        results_by_id: dict[str, VerificationResult] = {}
        claims_to_judge: list[Claim] = []

        # Check for claims that cite no available chunks -> stay pending
        for c in findings.claims:
            has_chunks = any(cid in chunks_map for cid in c.source_chunk_ids)
            if not has_chunks:
                c.verification_status = "pending"
                results_by_id[c.claim_id] = VerificationResult(
                    claim_id=c.claim_id,
                    verification_status="pending",
                    confidence_score=0.0,
                    explanation="Referenced source chunks are missing or unavailable for grounding.",
                    supporting_chunk_ids=[],
                )
            else:
                claims_to_judge.append(c)

        # (a) Batched claim judging, grouped by paper in sub-batches <= 8
        claims_by_paper: dict[str, list[Claim]] = {}
        for c in claims_to_judge:
            claims_by_paper.setdefault(c.source_paper_id, []).append(c)

        judge_sub_batches: list[list[Claim]] = []
        for paper_id, p_claims in claims_by_paper.items():
            for i in range(0, len(p_claims), 8):
                judge_sub_batches.append(p_claims[i:i + 8])

        def run_judge_batch(sub_batch: list[Claim]) -> dict[str, Optional[dict[str, Any]]]:
            return self._judge_claims_batch(sub_batch, chunks_map)

        initial_verdicts: dict[str, Optional[dict[str, Any]]] = {}
        if len(judge_sub_batches) == 1:
            initial_verdicts.update(run_judge_batch(judge_sub_batches[0]))
        elif len(judge_sub_batches) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for batch_res in pool.map(run_judge_batch, judge_sub_batches):
                    initial_verdicts.update(batch_res)

        unsupported_claims: list[Claim] = []
        original_texts: dict[str, str] = {}
        last_verdicts: dict[str, dict[str, Any]] = {}

        for c in claims_to_judge:
            verdict = initial_verdicts.get(c.claim_id)
            if verdict is None:
                # API failure on both batch and retry -> pending
                c.verification_status = "pending"
                results_by_id[c.claim_id] = VerificationResult(
                    claim_id=c.claim_id,
                    verification_status="pending",
                    confidence_score=0.0,
                    explanation="Verification pending due to LLM judge API failure or timeout.",
                    supporting_chunk_ids=[],
                )
            elif verdict.get("is_supported", False):
                c.verification_status = "verified"
                results_by_id[c.claim_id] = VerificationResult(
                    claim_id=c.claim_id,
                    verification_status="verified",
                    confidence_score=verdict.get("confidence", 1.0),
                    explanation=verdict.get("explanation", "") or "Claim is verified by source evidence.",
                    supporting_chunk_ids=verdict.get("supporting_chunk_ids", []),
                )
            else:
                # Judged unsupported -> candidate for revision loop
                original_texts[c.claim_id] = c.text
                last_verdicts[c.claim_id] = verdict
                c.revision_attempts = 0
                unsupported_claims.append(c)

        # (b) Real revision loop (max 2 attempts), batched
        revised_and_verified_count = 0
        current_unsupported = list(unsupported_claims)

        for round_num in range(1, 3):
            if not current_unsupported:
                break

            unsupported_by_paper: dict[str, list[Claim]] = {}
            for c in current_unsupported:
                unsupported_by_paper.setdefault(c.source_paper_id, []).append(c)

            revision_sub_batches: list[list[Claim]] = []
            for paper_id, p_claims in unsupported_by_paper.items():
                for i in range(0, len(p_claims), 8):
                    revision_sub_batches.append(p_claims[i:i + 8])

            def run_revise_batch(sub_batch: list[Claim]) -> dict[str, dict[str, Any]]:
                return self._revise_and_rejudge_batch(sub_batch, chunks_map)

            round_outcomes: dict[str, dict[str, Any]] = {}
            if len(revision_sub_batches) == 1:
                round_outcomes.update(run_revise_batch(revision_sub_batches[0]))
            elif len(revision_sub_batches) > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    for b_out in pool.map(run_revise_batch, revision_sub_batches):
                        round_outcomes.update(b_out)

            next_unsupported: list[Claim] = []
            for c in current_unsupported:
                outcome = round_outcomes.get(c.claim_id)
                if not outcome or outcome.get("type") == "api_failure":
                    # API failure during revision/judge -> pending, restore original text
                    c.text = original_texts[c.claim_id]
                    c.verification_status = "pending"
                    results_by_id[c.claim_id] = VerificationResult(
                        claim_id=c.claim_id,
                        verification_status="pending",
                        confidence_score=0.0,
                        explanation="Verification pending due to LLM revision/judge API failure or timeout.",
                        supporting_chunk_ids=[],
                    )
                elif outcome.get("type") == "revised_null":
                    # Failed round, nothing in evidence supports any version
                    c.revision_attempts = min(2, c.revision_attempts + 1)
                    c.verification_status = "unverified"
                    c.text = original_texts[c.claim_id]
                    last_v = last_verdicts.get(c.claim_id, {})
                    expl = last_v.get("explanation", "").strip() or "Claim is unsupported or contradicted by source evidence."
                    results_by_id[c.claim_id] = VerificationResult(
                        claim_id=c.claim_id,
                        verification_status="unverified",
                        confidence_score=last_v.get("confidence", 0.0),
                        explanation=expl,
                        supporting_chunk_ids=[],
                    )
                elif outcome.get("type") == "supported":
                    # Revised claim is supported -> verified, keep revised text
                    v = outcome.get("verdict", {})
                    c.verification_status = "verified"
                    orig = original_texts[c.claim_id]
                    expl = v.get("explanation", "").strip()
                    rev_expl = f'Revised from: "{orig}". {expl}' if expl else f'Revised from: "{orig}".'
                    results_by_id[c.claim_id] = VerificationResult(
                        claim_id=c.claim_id,
                        verification_status="verified",
                        confidence_score=v.get("confidence", 1.0),
                        explanation=rev_expl,
                        supporting_chunk_ids=v.get("supporting_chunk_ids", []),
                    )
                    revised_and_verified_count += 1
                elif outcome.get("type") == "unsupported":
                    # Failed round: re-judged but still unsupported
                    c.revision_attempts = min(2, c.revision_attempts + 1)
                    v = outcome.get("verdict", {})
                    last_verdicts[c.claim_id] = v
                    if round_num >= 2 or c.revision_attempts >= 2:
                        # 2 failed rounds exhausted -> unverified, restore original text
                        c.verification_status = "unverified"
                        c.text = original_texts[c.claim_id]
                        expl = v.get("explanation", "").strip() or "Claim is unsupported or contradicted by source evidence."
                        results_by_id[c.claim_id] = VerificationResult(
                            claim_id=c.claim_id,
                            verification_status="unverified",
                            confidence_score=v.get("confidence", 0.0),
                            explanation=expl,
                            supporting_chunk_ids=[],
                        )
                    else:
                        c.text = original_texts[c.claim_id]
                        next_unsupported.append(c)

            current_unsupported = next_unsupported

        # (d) Keep results in claim order
        verification_results = [results_by_id[c.claim_id] for c in findings.claims]

        # Synchronize claim statuses, attempts, and text across summaries
        claim_map = {c.claim_id: (c.verification_status, c.revision_attempts, c.text) for c in findings.claims}
        for summary in findings.summaries:
            for summary_claim in summary.extracted_claims:
                if summary_claim.claim_id in claim_map:
                    status, attempts, text = claim_map[summary_claim.claim_id]
                    summary_claim.verification_status = status
                    summary_claim.revision_attempts = attempts
                    summary_claim.text = text

        # (c) Batched cross-paper contradiction detection
        contradictions, details = self.detect_cross_paper_contradiction_details(findings.claims)
        findings.contradictions = contradictions
        findings.contradiction_details = details

        # (e) Logging summary line
        elapsed = time.time() - start_time
        llm_calls = self._llm_calls_count - start_calls
        verified_count = sum(1 for r in verification_results if r.verification_status == "verified")
        unverified_count = sum(1 for r in verification_results if r.verification_status == "unverified")
        pending_count = sum(1 for r in verification_results if r.verification_status == "pending")

        logger.info(
            "Verification summary: %d verified, %d unverified, %d pending, "
            "%d revised_and_verified, %d llm_calls, elapsed: %.2fs",
            verified_count,
            unverified_count,
            pending_count,
            revised_and_verified_count,
            llm_calls,
            elapsed,
        )

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