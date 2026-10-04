"""
Tests for batched claim verification, revision loop, and cross-paper contradiction detection.
Mocks _call_gemini_json so no external API calls are made.
"""

from unittest.mock import MagicMock, patch

from backend.agents.verification.agent import VerificationAgent, run_verification
from backend.schemas.schemas import (
    Chunk,
    Claim,
    FindingsPacket,
    IngestionResult,
    PaperMetadata,
    PaperSummary,
)


def _build_test_data():
    chunks_map = {
        "p1:c1": Chunk(chunk_id="p1:c1", paper_id="p1", text="Paper 1 mentions 92% accuracy on English benchmarks."),
        "p1:c2": Chunk(chunk_id="p1:c2", paper_id="p1", text="Paper 1 uses a transformer architecture."),
        "p2:c1": Chunk(chunk_id="p2:c1", paper_id="p2", text="Paper 2 mentions 85% accuracy on English benchmarks."),
    }
    return chunks_map


def test_missing_claim_id_in_batch_response():
    """
    When a batch response omits a claim_id, it is treated as not judged
    and retried once through the per-claim path.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="Claim 1 text", source_paper_id="p1", source_chunk_ids=["p1:c1"])
    c2 = Claim(claim_id="c2", text="Claim 2 text", source_paper_id="p1", source_chunk_ids=["p1:c2"])
    findings = FindingsPacket(topic="NLP", claims=[c1, c2])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        # Initial batch judge: returns verdict only for c1, c2 is missing
        if "CLAIMS TO VERIFY:" in prompt:
            if "Claim ID: c1" in prompt and "Claim ID: c2" in prompt:
                return {
                    "verdicts": [
                        {
                            "claim_id": "c1",
                            "is_supported": True,
                            "confidence": 0.95,
                            "explanation": "Supported by chunk p1:c1",
                            "supporting_chunk_ids": ["p1:c1"],
                        }
                    ]
                }
        # Per-claim retry for c2
        if "CLAIM:\nClaim 2 text" in prompt:
            return {
                "is_supported": True,
                "confidence": 0.88,
                "explanation": "Supported via per-claim retry",
            }
        if "contradictions" in prompt.lower():
            return {"contradictions": []}
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert results[0].claim_id == "c1"
    assert results[0].verification_status == "verified"
    assert results[1].claim_id == "c2"
    assert results[1].verification_status == "verified"
    assert results[1].explanation == "Supported via per-claim retry"


def test_missing_claim_id_retry_fails_marks_pending():
    """
    When a batch response omits a claim_id, and the per-claim retry also fails,
    the claim must be marked 'pending'.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="Claim 1 text", source_paper_id="p1", source_chunk_ids=["p1:c1"])
    c2 = Claim(claim_id="c2", text="Claim 2 text", source_paper_id="p1", source_chunk_ids=["p1:c2"])
    findings = FindingsPacket(topic="NLP", claims=[c1, c2])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        if "CLAIMS TO VERIFY:" in prompt and "Claim ID: c1" in prompt and "Claim ID: c2" in prompt:
            # c2 omitted from batch response
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": True,
                        "confidence": 0.95,
                        "explanation": "Supported",
                        "supporting_chunk_ids": ["p1:c1"],
                    }
                ]
            }
        # Per-claim retry for c2 fails (returns None)
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert results[0].verification_status == "verified"
    assert results[1].verification_status == "pending"
    assert updated_findings.claims[1].verification_status == "pending"


def test_malformed_batch_response_falls_back_to_per_claim():
    """
    When a batch judge response is malformed or invalid JSON structure,
    claims are retried once through per-claim path.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="Claim 1 text", source_paper_id="p1", source_chunk_ids=["p1:c1"])
    findings = FindingsPacket(topic="NLP", claims=[c1])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        if "CLAIMS TO VERIFY:" in prompt:
            # Return malformed structure
            return {"wrong_key": []}
        if "CLAIM:\nClaim 1 text" in prompt:
            # Per-claim fallback succeeds
            return {
                "is_supported": True,
                "confidence": 0.9,
                "explanation": "Supported via single fallback",
            }
        return {"contradictions": []}

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert results[0].verification_status == "verified"
    assert updated_findings.claims[0].verification_status == "verified"


def test_revision_success_path():
    """
    An unsupported claim is rewritten and re-judged. When the revised claim is supported:
    - verification_status = "verified"
    - claim.text is updated to revised text
    - explanation prepends 'Revised from: "<original text>".'
    - summary.extracted_claims syncs text and status
    """
    chunks_map = _build_test_data()
    original_text = "The model achieved 99% accuracy across all global languages."
    revised_text = "The model achieved 92% accuracy on English benchmarks."

    c1 = Claim(
        claim_id="c1",
        text=original_text,
        source_paper_id="p1",
        source_chunk_ids=["p1:c1"],
    )
    summary = PaperSummary(
        paper_id="p1",
        summary="Summary text",
        extracted_claims=[
            Claim(
                claim_id="c1",
                text=original_text,
                source_paper_id="p1",
                source_chunk_ids=["p1:c1"],
            )
        ],
    )
    findings = FindingsPacket(topic="NLP", summaries=[summary], claims=[c1])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        # 1. Initial batch judge -> unsupported
        if "CLAIMS TO VERIFY:" in prompt and original_text in prompt:
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": False,
                        "confidence": 0.8,
                        "explanation": "Evidence specifies English only, not all languages.",
                        "supporting_chunk_ids": [],
                    }
                ]
            }
        # 2. Revision rewrite
        if "CLAIMS TO REWRITE:" in prompt:
            return {
                "revisions": [
                    {
                        "claim_id": "c1",
                        "revised_text": revised_text,
                    }
                ]
            }
        # 3. Re-judge batch with revised text -> supported
        if "CLAIMS TO VERIFY:" in prompt and revised_text in prompt:
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": True,
                        "confidence": 0.95,
                        "explanation": "Directly matches chunk p1:c1.",
                        "supporting_chunk_ids": ["p1:c1"],
                    }
                ]
            }
        if "contradictions" in prompt.lower():
            return {"contradictions": []}
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert len(results) == 1
    res = results[0]
    assert res.verification_status == "verified"
    assert res.explanation.startswith(f'Revised from: "{original_text}".')
    assert updated_findings.claims[0].text == revised_text
    assert updated_findings.claims[0].verification_status == "verified"
    # Verify summary sync
    assert updated_findings.summaries[0].extracted_claims[0].text == revised_text
    assert updated_findings.summaries[0].extracted_claims[0].verification_status == "verified"


def test_revision_failure_path_ends_unverified():
    """
    When a claim fails 2 revision rounds:
    - ends with verification_status = "unverified"
    - original claim text is restored
    - revision_attempts == 2
    """
    chunks_map = _build_test_data()
    original_text = "The system achieved full general artificial intelligence."

    c1 = Claim(
        claim_id="c1",
        text=original_text,
        source_paper_id="p1",
        source_chunk_ids=["p1:c1"],
    )
    summary = PaperSummary(
        paper_id="p1",
        summary="Summary text",
        extracted_claims=[
            Claim(
                claim_id="c1",
                text=original_text,
                source_paper_id="p1",
                source_chunk_ids=["p1:c1"],
            )
        ],
    )
    findings = FindingsPacket(topic="AI", summaries=[summary], claims=[c1])

    agent = VerificationAgent(api_key="fake-key")

    call_count = {"rewrite": 0, "rejudge": 0}

    def mock_call(prompt: str):
        # Initial judge -> unsupported
        if "CLAIMS TO VERIFY:" in prompt and call_count["rejudge"] == 0 and original_text in prompt:
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": False,
                        "confidence": 0.9,
                        "explanation": "Not mentioned in evidence.",
                        "supporting_chunk_ids": [],
                    }
                ]
            }
        # Rewrites (round 1 and round 2)
        if "CLAIMS TO REWRITE:" in prompt:
            call_count["rewrite"] += 1
            return {
                "revisions": [
                    {
                        "claim_id": "c1",
                        "revised_text": f"Attempt {call_count['rewrite']} text",
                    }
                ]
            }
        # Re-judging revised claims -> unsupported
        if "CLAIMS TO VERIFY:" in prompt and "Attempt" in prompt:
            call_count["rejudge"] += 1
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": False,
                        "confidence": 0.85,
                        "explanation": "Still unsupported.",
                        "supporting_chunk_ids": [],
                    }
                ]
            }
        if "contradictions" in prompt.lower():
            return {"contradictions": []}
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert len(results) == 1
    res = results[0]
    assert res.verification_status == "unverified"
    assert updated_findings.claims[0].verification_status == "unverified"
    assert updated_findings.claims[0].text == original_text
    assert updated_findings.claims[0].revision_attempts == 2
    # Sync check
    assert updated_findings.summaries[0].extracted_claims[0].text == original_text
    assert updated_findings.summaries[0].extracted_claims[0].revision_attempts == 2
    assert updated_findings.summaries[0].extracted_claims[0].verification_status == "unverified"


def test_revision_null_revised_text_terminates_immediately():
    """
    If Gemini returns revised_text = null because nothing in evidence supports any version,
    the revision ends unverified and restores original text.
    """
    chunks_map = _build_test_data()
    original_text = "Completely unsupported statement."

    c1 = Claim(
        claim_id="c1",
        text=original_text,
        source_paper_id="p1",
        source_chunk_ids=["p1:c1"],
    )
    findings = FindingsPacket(topic="AI", claims=[c1])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        if "CLAIMS TO VERIFY:" in prompt and original_text in prompt:
            return {
                "verdicts": [
                    {
                        "claim_id": "c1",
                        "is_supported": False,
                        "confidence": 0.9,
                        "explanation": "Unsupported.",
                        "supporting_chunk_ids": [],
                    }
                ]
            }
        if "CLAIMS TO REWRITE:" in prompt:
            return {
                "revisions": [
                    {
                        "claim_id": "c1",
                        "revised_text": None,
                    }
                ]
            }
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert results[0].verification_status == "unverified"
    assert updated_findings.claims[0].text == original_text
    assert updated_findings.claims[0].verification_status == "unverified"
    assert updated_findings.claims[0].revision_attempts == 1


def test_contradiction_response_with_bad_id():
    """
    Batched contradiction detection must ignore pairs whose ids don't belong
    to the right papers, and retain valid cross-paper contradictions.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="Method A accuracy is 92%.", source_paper_id="p1", source_chunk_ids=["p1:c1"])
    c2 = Claim(claim_id="c2", text="Method A accuracy is 50%.", source_paper_id="p2", source_chunk_ids=["p2:c1"])
    findings = FindingsPacket(topic="Benchmark", claims=[c1, c2])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        if "CLAIMS TO VERIFY:" in prompt:
            if "Claim ID: c1" in prompt:
                return {
                    "verdicts": [
                        {
                            "claim_id": "c1",
                            "is_supported": True,
                            "confidence": 0.9,
                            "explanation": "OK",
                            "supporting_chunk_ids": ["p1:c1"],
                        }
                    ]
                }
            if "Claim ID: c2" in prompt:
                return {
                    "verdicts": [
                        {
                            "claim_id": "c2",
                            "is_supported": True,
                            "confidence": 0.9,
                            "explanation": "OK",
                            "supporting_chunk_ids": ["p2:c1"],
                        }
                    ]
                }
        if "contradictions" in prompt.lower():
            return {
                "contradictions": [
                    # Invalid pair with non-existent id
                    {
                        "claim_a_id": "c1",
                        "claim_b_id": "ghost_claim_999",
                        "explanation": "Invalid ghost conflict.",
                    },
                    # Invalid pair with both from p1
                    {
                        "claim_a_id": "c1",
                        "claim_b_id": "c1",
                        "explanation": "Same paper conflict.",
                    },
                    # Valid cross-paper contradiction
                    {
                        "claim_a_id": "c1",
                        "claim_b_id": "c2",
                        "shared_subject": "Method A accuracy",
                        "explanation": "Directly conflicting accuracy measurements.",
                    },
                ]
            }
        return None

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert len(updated_findings.contradictions) == 1
    expected = "Claim 'c1' conflicts with claim 'c2': Directly conflicting accuracy measurements."
    assert updated_findings.contradictions[0] == expected


def test_claim_without_evidence_stays_pending():
    """
    A claim citing chunks not available in chunks_map stays pending without calling LLM judge.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="No evidence available.", source_paper_id="p1", source_chunk_ids=["missing_chunk"])
    findings = FindingsPacket(topic="Test", claims=[c1])

    agent = VerificationAgent(api_key="fake-key")

    with patch.object(agent, "_call_gemini_json") as mock_gemini:
        updated_findings, results = agent.verify_findings(findings, chunks_map)
        mock_gemini.assert_not_called()

    assert results[0].verification_status == "pending"
    assert updated_findings.claims[0].verification_status == "pending"
    assert "missing or unavailable" in results[0].explanation


def test_results_preserve_original_claim_order():
    """
    VerificationResult list must strictly match the order of findings.claims,
    even across multiple papers and batching.
    """
    chunks_map = _build_test_data()
    c1 = Claim(claim_id="c1", text="P1 claim 1", source_paper_id="p1", source_chunk_ids=["p1:c1"])
    c2 = Claim(claim_id="c2", text="P2 claim 1", source_paper_id="p2", source_chunk_ids=["p2:c1"])
    c3 = Claim(claim_id="c3", text="P1 claim 2", source_paper_id="p1", source_chunk_ids=["p1:c2"])
    findings = FindingsPacket(topic="OrderTest", claims=[c2, c1, c3])

    agent = VerificationAgent(api_key="fake-key")

    def mock_call(prompt: str):
        if "CLAIMS TO VERIFY:" in prompt:
            verdicts = []
            for cid in ["c1", "c2", "c3"]:
                if f"Claim ID: {cid}" in prompt:
                    verdicts.append(
                        {
                            "claim_id": cid,
                            "is_supported": True,
                            "confidence": 0.9,
                            "explanation": "Supported",
                            "supporting_chunk_ids": [],
                        }
                    )
            return {"verdicts": verdicts}
        return {"contradictions": []}

    with patch.object(agent, "_call_gemini_json", side_effect=mock_call):
        updated_findings, results = agent.verify_findings(findings, chunks_map)

    assert [r.claim_id for r in results] == ["c2", "c1", "c3"]
    assert [c.claim_id for c in updated_findings.claims] == ["c2", "c1", "c3"]
