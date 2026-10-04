"""
Standalone test for Summarization + Verification agents, WITHOUT hitting the
real Gemini API (uses a scripted FakeGeminiClient). This is the
"test your agent in isolation before it's plugged into the Orchestrator"
step from the General Rules.

Run:
    python -m tests.agents.test_summarization_verification_standalone
"""
from backend.agents.summarization.agent import run_summarization
from backend.agents.verification.agent import run_verification
from backend.schemas.schemas import Chunk, IngestionResult, PaperMetadata


class FakeGeminiClient:
    """Scripted stand-in for GeminiClient so this test needs no API key and no quota."""

    def generate(self, prompt, *, paper_id, agent_name, purpose, use_cache=True):
        if purpose == "per_paper_summary_and_claims":
            return (
                "SUMMARY: The paper reports strong benchmark results.\n"
                "KEY_FINDINGS:\n- High accuracy achieved\n"
                "CLAIMS:\n- claim: The model achieved 92% accuracy. | chunk_id: p1:c0\n"
            )
        if purpose == "cross_paper_synthesis":
            return "The paper reports strong empirical results on its benchmark."
        if purpose == "grounding_check":
            return '{"status": "verified", "confidence": 0.9, "reason": "Matches source text."}'
        if purpose == "contradiction_check":
            return "NO"
        return ""


def test_pipeline_runs_end_to_end_offline():
    ingestion_results = [
        IngestionResult(
            paper_id="p1",
            metadata=PaperMetadata(paper_id="p1", title="Test Paper"),
            chunks=[Chunk(chunk_id="p1:c0", paper_id="p1", text="The model achieved 92% accuracy.")],
            raw_text="The model achieved 92% accuracy.",
        )
    ]

    client = FakeGeminiClient()

    findings = run_summarization("model accuracy", ingestion_results, client=client)
    assert findings.claims, "Summarization should have produced at least one claim"
    assert findings.claims[0].source_chunk_ids == ["p1:c0"]

    results, updated_findings = run_verification(findings, ingestion_results, client=client)
    assert results[0].verification_status == "verified"
    assert updated_findings.claims[0].verification_status == "verified"

    print("OK: summarization + verification standalone test passed.")


if __name__ == "__main__":
    test_pipeline_runs_end_to_end_offline()
