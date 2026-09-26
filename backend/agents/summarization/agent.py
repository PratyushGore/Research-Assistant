from backend.schemas.schemas import (
    IngestionResult,
    PaperSummary,
    FindingsPacket,
    Claim,
)


def summarize_text(text: str, max_sentences: int = 5) -> str:
    """
    Create a simple extractive summary from text.

    This version does not require an external LLM/API.
    It selects the first meaningful sentences from the text.
    """

    if not text or not text.strip():
        return ""

    text = " ".join(text.split())

    # Basic sentence splitting.
    sentences = []

    for part in text.replace("!", ".").replace("?", ".").split("."):
        sentence = part.strip()

        if sentence:
            sentences.append(sentence)

    selected = sentences[:max_sentences]

    if not selected:
        return text[:1000]

    return ". ".join(selected) + "."


def extract_key_findings(
    text: str,
    max_findings: int = 5,
) -> list[str]:
    """
    Extract important-looking sentences as key findings.

    This is intentionally lightweight and deterministic.
    """

    if not text or not text.strip():
        return []

    text = " ".join(text.split())

    sentences = []

    for part in text.replace("!", ".").replace("?", ".").split("."):
        sentence = part.strip()

        if len(sentence) >= 40:
            sentences.append(sentence)

    return sentences[:max_findings]


def create_claims(
    paper_id: str,
    findings: list[str],
) -> list[Claim]:
    """
    Convert extracted findings into Claim objects.
    """

    claims = []

    for index, finding in enumerate(findings):
        claims.append(
            Claim(
                claim_id=f"{paper_id}:claim:{index}",
                text=finding,
                source_paper_id=paper_id,
                source_chunk_ids=[],
                verification_status="pending",
                revision_attempts=0,
            )
        )

    return claims


def summarize_paper(
    ingestion_result: IngestionResult,
) -> PaperSummary:
    """
    Summarize one ingested research paper.
    """

    paper_id = ingestion_result.paper_id

    raw_text = ingestion_result.raw_text or ""

    summary = summarize_text(raw_text)

    key_findings = extract_key_findings(raw_text)

    claims = create_claims(
        paper_id=paper_id,
        findings=key_findings,
    )

    return PaperSummary(
        paper_id=paper_id,
        summary=summary,
        key_findings=key_findings,
        extracted_claims=claims,
    )


def summarize_papers(
    ingestion_results: list[IngestionResult],
    topic: str,
) -> FindingsPacket:
    """
    Summarize all successfully ingested papers.
    """

    summaries = []
    all_claims = []

    for result in ingestion_results:
        # Skip papers where no text could be extracted.
        if not result.raw_text:
            print(
                f"[Summarization Agent] "
                f"Skipping {result.paper_id}: no text available."
            )
            continue

        print(
            f"[Summarization Agent] "
            f"Summarizing: {result.metadata.title}"
        )

        paper_summary = summarize_paper(result)

        summaries.append(paper_summary)

        all_claims.extend(
            paper_summary.extracted_claims
        )

    print(
        f"[Summarization Agent] "
        f"{len(summaries)} papers summarized."
    )

    return FindingsPacket(
        topic=topic,
        summaries=summaries,
        claims=all_claims,
    )