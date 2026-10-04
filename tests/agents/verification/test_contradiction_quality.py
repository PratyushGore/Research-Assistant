from unittest.mock import patch

from backend.agents.verification.agent import VerificationAgent
from backend.orchestrator.graph import summarization_agent
from backend.schemas.schemas import (
    Claim,
    ContradictionDetail,
    FindingsPacket,
    IngestionResult,
    PaperMetadata,
    PaperSummary,
)


def test_approach_difference_returns_no_contradiction_and_prompt_contains_rule():
    """
    (1) The approach-difference example returns NO contradiction when the mocked judge
    returns an empty list, and the prompt text sent to the judge contains the new
    'same quantity/setting' rule.
    """
    c1 = Claim(
        claim_id="arxiv:1905.09130v1:claim:0",
        text="uses ML prediction + optimization",
        source_paper_id="arxiv:1905.09130v1",
        verification_status="verified",
    )
    c2 = Claim(
        claim_id="arxiv:2104.05555v1:claim:0",
        text="data-driven approach that needs no demand forecasting",
        source_paper_id="arxiv:2104.05555v1",
        verification_status="verified",
    )

    agent = VerificationAgent(api_key="fake-key")
    captured_prompts: list[str] = []

    def mock_gemini(prompt: str):
        captured_prompts.append(prompt)
        return {"contradictions": []}

    with patch.object(agent, "_call_gemini_json", side_effect=mock_gemini):
        strings, details = agent.detect_cross_paper_contradiction_details([c1, c2])

    assert strings == []
    assert details == []
    assert len(captured_prompts) == 1

    prompt_text = captured_prompts[0]
    # Verify strict contradiction definition rule is in the prompt
    assert "SAME quantity" in prompt_text or "same quantity" in prompt_text.lower()
    assert "setting" in prompt_text.lower()
    assert "not contradictions" in prompt_text.lower()


def test_two_judge_items_sharing_claim_a_merge_into_one_detail():
    """
    (2) Two judge items sharing claim_a merge into one detail with extra_claim_ids
    and one string.
    """
    c1 = Claim(
        claim_id="c1",
        text="Peak inference throughput reaches 1000 req/s.",
        source_paper_id="p1",
        verification_status="verified",
    )
    c2 = Claim(
        claim_id="c2",
        text="Peak inference throughput tops out at 200 req/s under identical load.",
        source_paper_id="p2",
        verification_status="verified",
    )
    c3 = Claim(
        claim_id="c3",
        text="Peak inference throughput never exceeds 220 req/s in identical benchmark.",
        source_paper_id="p3",
        verification_status="verified",
    )

    agent = VerificationAgent(api_key="fake-key")

    def mock_gemini(prompt: str):
        if "Paper B ('p2')" in prompt:
            return {
                "contradictions": [
                    {
                        "claim_a_id": "c1",
                        "claim_b_id": "c2",
                        "shared_subject": "Peak inference throughput",
                        "explanation": "P1 reports 1000 req/s vs P2 reports 200 req/s",
                    }
                ]
            }
        if "Paper B ('p3')" in prompt:
            return {
                "contradictions": [
                    {
                        "claim_a_id": "c1",
                        "claim_b_id": "c3",
                        "shared_subject": "Peak inference throughput",
                        "explanation": "P1 reports 1000 req/s vs P3 reports 220 req/s",
                    }
                ]
            }
        return {"contradictions": []}

    with patch.object(agent, "_call_gemini_json", side_effect=mock_gemini):
        strings, details = agent.detect_cross_paper_contradiction_details([c1, c2, c3])

    # Must be merged into ONE detail with extra_claim_ids and ONE string
    assert len(details) == 1
    assert details[0].claim_a_id == "c1"
    assert details[0].claim_b_id == "c2"
    assert "c3" in details[0].extra_claim_ids
    assert details[0].shared_subject == "Peak inference throughput"

    assert len(strings) == 1
    assert strings[0].startswith("Claim 'c1' conflicts with claim 'c2':")
    assert "1000 req/s" in strings[0]


def test_item_without_shared_subject_is_dropped():
    """
    (3) Item without shared_subject is dropped; only items with valid shared_subject
    and valid paper IDs are kept.
    """
    c1 = Claim(
        claim_id="c1",
        text="Algorithm accuracy is 95%.",
        source_paper_id="p1",
        verification_status="verified",
    )
    c2 = Claim(
        claim_id="c2",
        text="Algorithm accuracy is 60%.",
        source_paper_id="p2",
        verification_status="verified",
    )
    c3 = Claim(
        claim_id="c3",
        text="Algorithm accuracy is 40%.",
        source_paper_id="p2",
        verification_status="verified",
    )

    agent = VerificationAgent(api_key="fake-key")

    def mock_gemini(prompt: str):
        return {
            "contradictions": [
                # Valid item with shared_subject
                {
                    "claim_a_id": "c1",
                    "claim_b_id": "c2",
                    "shared_subject": "Algorithm classification accuracy",
                    "explanation": "Conflicting accuracy rates on the same benchmark.",
                },
                # Invalid: missing shared_subject
                {
                    "claim_a_id": "c1",
                    "claim_b_id": "c3",
                    "explanation": "Accuracy numbers do not match.",
                },
                # Invalid: empty string shared_subject
                {
                    "claim_a_id": "c1",
                    "claim_b_id": "c3",
                    "shared_subject": "   ",
                    "explanation": "Empty shared subject.",
                },
            ]
        }

    with patch.object(agent, "_call_gemini_json", side_effect=mock_gemini):
        strings, details = agent.detect_cross_paper_contradiction_details([c1, c2, c3])

    assert len(details) == 1
    assert details[0].claim_a_id == "c1"
    assert details[0].claim_b_id == "c2"
    assert details[0].shared_subject == "Algorithm classification accuracy"

    assert len(strings) == 1
    assert "c2" in strings[0]
    assert "c3" not in strings[0]


def test_paper_summary_metadata_populated_in_summarize_node():
    """
    (4) PaperSummary metadata is populated from ingestion metadata in the summarize node,
    and left empty when absent.
    """
    ir1 = IngestionResult(
        paper_id="p1",
        metadata=PaperMetadata(
            paper_id="p1",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer"],
            year=2017,
            venue="NeurIPS",
            url="https://arxiv.org/abs/1706.03762",
        ),
    )
    ir2 = IngestionResult(
        paper_id="p2",
        metadata=PaperMetadata(
            paper_id="p2",
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            authors=["Jacob Devlin"],
            year=2018,
            venue=None,
            url=None,
        ),
    )
    from unittest.mock import MagicMock
    ir3 = MagicMock(paper_id="p3", metadata=None)

    state = {
        "research_topic": "Transformer Architectures",
        "ingestion_results": [ir1, ir2, ir3],
    }

    mock_findings = FindingsPacket(
        topic="Transformer Architectures",
        summaries=[
            PaperSummary(paper_id="p1", summary="Summary for P1"),
            PaperSummary(paper_id="p2", summary="Summary for P2"),
            PaperSummary(paper_id="p3", summary="Summary for P3"),
            PaperSummary(paper_id="p_unknown", summary="Summary for uningested paper"),
        ],
        claims=[],
    )

    with patch("backend.agents.summarization.agent.run_summarization", return_value=mock_findings):
        new_state = summarization_agent(state)

    summaries = new_state["findings"].summaries
    assert len(summaries) == 4

    # p1 fully populated
    assert summaries[0].paper_id == "p1"
    assert summaries[0].title == "Attention Is All You Need"
    assert summaries[0].authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert summaries[0].year == 2017
    assert summaries[0].venue == "NeurIPS"
    assert summaries[0].url == "https://arxiv.org/abs/1706.03762"

    # p2 partially populated
    assert summaries[1].paper_id == "p2"
    assert summaries[1].title == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert summaries[1].authors == ["Jacob Devlin"]
    assert summaries[1].year == 2018
    assert summaries[1].venue is None
    assert summaries[1].url is None

    # p3 metadata is None -> left empty
    assert summaries[2].paper_id == "p3"
    assert summaries[2].title is None
    assert summaries[2].authors == []
    assert summaries[2].year is None

    # p_unknown not in ingestion_results -> left empty
    assert summaries[3].paper_id == "p_unknown"
    assert summaries[3].title is None
    assert summaries[3].authors == []
    assert summaries[3].year is None


def test_findings_packet_validates_and_dumps_without_new_fields():
    """
    (5) FindingsPacket still validates and dumps without the new fields.
    """
    # 1. Fresh instantiation without optional fields
    packet = FindingsPacket(topic="Robust Verification")
    assert packet.contradictions == []
    assert packet.contradiction_details == []
    dump = packet.model_dump()
    assert dump["topic"] == "Robust Verification"
    assert dump["contradictions"] == []
    assert dump["contradiction_details"] == []

    # 2. Deserializing legacy payload lacking contradiction_details and paper metadata
    legacy_payload = {
        "topic": "Legacy Research",
        "summaries": [
            {
                "paper_id": "legacy_p1",
                "summary": "Summary text without title or authors.",
                "key_findings": ["Finding 1"],
            }
        ],
        "claims": [],
        "contradictions": [
            "Claim 'c1' conflicts with claim 'c2': Conflicting results."
        ],
    }

    validated = FindingsPacket.model_validate(legacy_payload)
    assert validated.topic == "Legacy Research"
    assert validated.contradiction_details == []
    assert len(validated.summaries) == 1
    assert validated.summaries[0].title is None
    assert validated.summaries[0].authors == []
    assert validated.summaries[0].year is None
    assert len(validated.contradictions) == 1
