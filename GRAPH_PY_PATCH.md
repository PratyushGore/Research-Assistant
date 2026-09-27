# Patch for `backend/orchestrator/graph.py`

Your teammate's `graph.py` currently has `summarization_agent` and
`verification_agent` implemented **inline** with deterministic (no-LLM)
logic. Replace the body of those two functions with the versions below,
which delegate to your new modules — matching the same pattern
`search_agent` / `ingestion_agent` / `composer_agent` already use.

Do not change the function names, signatures, or how they're wired into
`builder.add_node(...)` — only the bodies below.

```python
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
```

## Where these files go in your repo

```
backend/
  agents/
    common/
      __init__.py
      llm_client.py          <- new: shared Gemini client + cache
    summarization/
      __init__.py
      agent.py                <- new: run_summarization(), revise_claim()
    verification/
      __init__.py
      agent.py                <- new: run_verification()
tests/
  agents/
    test_summarization_verification_standalone.py   <- new: offline test
    test_accuracy_harness.py                          <- new: Week-3 metric
```

## Before you push

1. `pip install google-generativeai` and add it to the project's
   `requirements.txt` (or use `requirements-personB.txt` provided here).
2. Set `GEMINI_API_KEY` in your environment (never commit it — add a
   `.env` entry and confirm it's covered by `.gitignore`).
3. Run the offline test first (no API key needed, no quota spent):
   ```
   python -m tests.agents.test_summarization_verification_standalone
   ```
4. Then a real smoke test against the live API:
   ```
   python -m tests.agents.test_accuracy_harness
   ```
5. Only after both pass, apply the `graph.py` patch above and commit.
