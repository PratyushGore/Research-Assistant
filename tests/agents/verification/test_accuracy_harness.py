"""
Week-3 accuracy harness (your headline metric): inject known false claims
into test papers and measure the Verification Agent's catch rate
(precision / recall).

Uses the REAL Gemini API by default (needs GEMINI_API_KEY set) since the
whole point is to measure the actual LLM-as-judge's catch rate - swap in
FakeGeminiClient only to sanity-check the harness's scoring logic itself,
not to report a real number.

Run:
    export GEMINI_API_KEY=your_key_here
    python -m tests.agents.test_accuracy_harness
"""
from backend.agents.verification.agent import run_verification
from backend.schemas.schemas import Chunk, Claim, FindingsPacket, IngestionResult, PaperMetadata


def _make_paper(paper_id: str, source_sentence: str) -> IngestionResult:
    return IngestionResult(
        paper_id=paper_id,
        metadata=PaperMetadata(paper_id=paper_id, title=f"Paper {paper_id}"),
        chunks=[Chunk(chunk_id=f"{paper_id}:c0", paper_id=paper_id, text=source_sentence)],
        raw_text=source_sentence,
    )


def build_test_set():
    """
    Returns (ingestion_results, findings, ground_truth) where ground_truth
    maps claim_id -> True (claim is actually supported by its source) or
    False (claim is a known injected false claim - should be caught).

    Extend this with real excerpts from your test papers before running
    the official Week-3 measurement; this seed set is a smaller sanity
    check (3 true / 3 false - scale to the 10-15 your brief calls for).
    """
    true_facts = [
        ("p1", "The model achieved 92% accuracy on the benchmark dataset."),
        ("p2", "Training used a batch size of 32 across 8 GPUs."),
        ("p3", "The dataset contains 10,000 labeled examples."),
    ]
    false_claims = [
        ("p1", "The model achieved 99.9% accuracy with zero errors."),
        ("p2", "Training used a single CPU with no GPU acceleration."),
        ("p3", "The dataset contains 1 million labeled examples."),
    ]

    ingestion_results = [_make_paper(pid, fact) for pid, fact in true_facts]

    claims = []
    ground_truth = {}

    for i, (pid, fact) in enumerate(true_facts):
        cid = f"{pid}:true:{i}"
        claims.append(Claim(claim_id=cid, text=fact, source_paper_id=pid, source_chunk_ids=[f"{pid}:c0"]))
        ground_truth[cid] = True

    for i, (pid, fake) in enumerate(false_claims):
        cid = f"{pid}:false:{i}"
        claims.append(Claim(claim_id=cid, text=fake, source_paper_id=pid, source_chunk_ids=[f"{pid}:c0"]))
        ground_truth[cid] = False

    findings = FindingsPacket(topic="accuracy harness", summaries=[], claims=claims)
    return ingestion_results, findings, ground_truth


def run_accuracy_harness(client=None):
    ingestion_results, findings, ground_truth = build_test_set()
    results, _ = run_verification(findings, ingestion_results, client=client)

    tp = fp = fn = tn = 0
    for r in results:
        actually_true = ground_truth[r.claim_id]
        predicted_verified = r.verification_status == "verified"

        if actually_true and predicted_verified:
            tp += 1
        elif not actually_true and not predicted_verified:
            tn += 1  # correctly caught an injected false claim
        elif not actually_true and predicted_verified:
            fp += 1  # MISSED a false claim - wrongly verified it
        else:
            fn += 1  # wrongly rejected a genuinely true claim

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    catch_rate = tn / (tn + fp) if (tn + fp) else 0.0  # recall on the injected false-claim class

    print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"Precision on claims marked 'verified': {precision:.2f}")
    print(f"Catch rate on injected false claims:    {catch_rate:.2f}  <-- headline number")

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "catch_rate": catch_rate}


if __name__ == "__main__":
    run_accuracy_harness()
