from pathlib import Path
from unittest.mock import MagicMock
import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm

from backend.agents.composer.doc_content import (
    build_doc_structured,
    extract_complete_short_clause,
    validate_results_table,
)
from backend.agents.output_renderer.docx_renderer import render_docx
from backend.schemas.schemas import (
    AcademicContentInfo,
    CitationResult,
    Claim,
    ComposerResult,
    ContentBlock,
    ContradictionDetail,
    CoverInfo,
    FindingsPacket,
    FormattedCitation,
    GuidedInputBundle,
    OutputType,
    PaperSummary,
    ProjectPresentationInfo,
)


def sample_guided_input(limitations: str = "Limited to benchmark datasets.") -> GuidedInputBundle:
    return GuidedInputBundle(
        cover_info=CoverInfo(
            title="Scalable Multi-Agent Research Architectures",
            subtitle="Autonomous Synthesis and Fact Verification",
            authors=["Dr. Alice Smith", "Bob Jones"],
            institution="AI Research Institute",
            date="October 2026",
        ),
        academic_content_info=AcademicContentInfo(
            methodology="Decoupled multi-agent orchestration using directed acyclic graphs.",
            dataset_or_sample="10,000 academic papers from arXiv Computer Science.",
            tools_used=["Python", "LangGraph", "PyTorch"],
            what_was_measured="Latency, throughput, and citation hallucination rate.",
            key_results="Latency reduced by 35%, recall reached 94.5%, and hallucinations dropped to 0.0%.",
            limitations=limitations,
        ),
        project_presentation_info=ProjectPresentationInfo(
            problem_statement="Manual literature research is bottlenecked by human reading speed.",
            tech_stack=["Python", "FastAPI", "React"],
            own_architecture_summary="Orchestrator manages ingestion retrieval verification composer agents in workflow.",
            own_results_summary="Throughput reached 42 requests per second with high factual accuracy.",
        ),
    )


def sample_findings(with_contradictions: bool = True) -> FindingsPacket:
    claims = [
        Claim(
            claim_id="claim_001",
            text="Dense retrieval models improve candidate recall by 28% over sparse BM25 baselines.",
            source_paper_id="paper_101",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_002",
            text="Cross-encoder re-ranking introduces significant computational overhead during inference.",
            source_paper_id="paper_101",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_003",
            text="Decoupled verification architectures reduce hallucinated citations in LLM outputs.",
            source_paper_id="paper_202",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_004",
            text="Single-prompt monolithic LLM summaries frequently invent non-existent paper titles.",
            source_paper_id="paper_303",
            verification_status="verified",
        ),
        Claim(
            claim_id="claim_unverified_005",
            text="Quantum computing completely obsoletes classical vector indexes.",
            source_paper_id="paper_404",
            verification_status="unverified",
        ),
    ]

    summaries = [
        PaperSummary(
            paper_id="paper_101",
            summary="Dense retrieval mechanisms evaluate candidate passages using embeddings.",
            title="Dense Retrieval in Academic Discovery",
            authors=["Zhang, Wei", "Chen, Lin"],
            year=2023,
            venue="SIGIR",
        ),
        PaperSummary(
            paper_id="paper_202",
            summary="Decoupled fact verification validates citations independently.",
            title="Decoupled Fact Verification for Language Models",
            authors=["Adams, John", "Baker, Chloe"],
            year=2024,
            venue="ACL",
        ),
        PaperSummary(
            paper_id="paper_303",
            summary="Hallucination mitigation through multi-stage prompting and citation checking.",
            title="Mitigating Hallucinations in Scholarly Generation",
            authors=["Miller, Sarah"],
            year=2025,
            venue="EMNLP",
        ),
    ]

    contra_details = []
    if with_contradictions:
        contra_details.append(
            ContradictionDetail(
                claim_a_id="claim_001",
                claim_b_id="claim_002",
                paper_a_id="paper_101",
                paper_b_id="paper_202",
                explanation="Paper 101 asserts dense retrieval latency is negligible, while Paper 202 finds multi-agent verification latency dominates.",
                shared_subject="Retrieval latency vs verification overhead",
            )
        )

    return FindingsPacket(
        topic="Multi-Agent Academic Synthesis",
        summaries=summaries,
        claims=claims,
        contradiction_details=contra_details,
    )


def sample_citations(style: str = "ieee") -> CitationResult:
    if style == "ieee":
        return CitationResult(
            citation_style="ieee",
            citations=[
                FormattedCitation(
                    citation_id="cit_101",
                    paper_id="paper_101",
                    citation_style="ieee",
                    inline_marker="[1]",
                    full_entry='[1] W. Zhang and L. Chen, "Dense Retrieval in Academic Discovery," SIGIR, 2023.',
                ),
                FormattedCitation(
                    citation_id="cit_202",
                    paper_id="paper_202",
                    citation_style="ieee",
                    inline_marker="[2]",
                    full_entry='[2] J. Adams and C. Baker, "Decoupled Fact Verification for Language Models," ACL, 2024.',
                ),
                FormattedCitation(
                    citation_id="cit_303",
                    paper_id="paper_303",
                    citation_style="ieee",
                    inline_marker="[3]",
                    full_entry='[3] S. Miller, "Mitigating Hallucinations in Scholarly Generation," EMNLP, 2025.',
                ),
            ],
            bibliography=[],
        )
    else:
        return CitationResult(
            citation_style="apa",
            citations=[
                FormattedCitation(
                    citation_id="cit_101",
                    paper_id="paper_101",
                    citation_style="apa",
                    inline_marker="(Zhang & Chen, 2023)",
                    full_entry="Zhang, W., & Chen, L. (2023). Dense Retrieval in Academic Discovery. SIGIR.",
                ),
                FormattedCitation(
                    citation_id="cit_202",
                    paper_id="paper_202",
                    citation_style="apa",
                    inline_marker="(Adams & Baker, 2024)",
                    full_entry="Adams, J., & Baker, C. (2024). Decoupled Fact Verification for Language Models. ACL.",
                ),
                FormattedCitation(
                    citation_id="cit_303",
                    paper_id="paper_303",
                    citation_style="apa",
                    inline_marker="(Miller, 2025)",
                    full_entry="Miller, S. (2025). Mitigating Hallucinations in Scholarly Generation. EMNLP.",
                ),
            ],
            bibliography=[],
        )


# ---------------------------------------------------------------------------
# Section Order Tests
# ---------------------------------------------------------------------------

def test_section_order_research_paper():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    structured = build_doc_structured(
        output_type=OutputType.RESEARCH_PAPER,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=None,
    )

    headings = [s.heading for s in structured.sections]

    assert headings[0] == "Front Matter"
    assert headings[1] == "Abstract"
    assert headings[2] == "Introduction"
    assert headings[3] == "Related Work"
    # Thematic and table subsections follow Related Work
    meth_idx = headings.index("Methodology")
    res_idx = headings.index("Results") if "Results" in headings else headings.index("Results and Discussion")
    lim_idx = headings.index("Limitations")
    concl_idx = headings.index("Conclusion and Future Work") if "Conclusion and Future Work" in headings else headings.index("Conclusion")
    ref_idx = headings.index("References")

    assert 3 < meth_idx < res_idx < lim_idx < concl_idx < ref_idx
    # Subsections start with "## "
    subsections = [h for h in headings if h.startswith("## ")]
    assert len(subsections) >= 2
    assert any(h.lower() == "## comparison with prior work" for h in headings)


def test_section_order_literature_survey():
    guided = sample_guided_input()
    findings = sample_findings(with_contradictions=True)
    citations = sample_citations("ieee")

    structured = build_doc_structured(
        output_type=OutputType.LITERATURE_SURVEY,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=None,
    )

    headings = [s.heading for s in structured.sections]

    assert headings[0] == "Front Matter"
    assert headings[1] == "Abstract"
    assert headings[2] == "Introduction"
    assert headings[3] == "Taxonomy of Surveyed Literature"

    comp_idx = headings.index("Comparative Analysis")
    contra_idx = headings.index("Conflicting and Open Findings")
    trends_idx = headings.index("Trends")
    gaps_idx = headings.index("Research Gaps and Future Directions")
    concl_idx = headings.index("Conclusion")
    ref_idx = headings.index("References")

    assert 3 < comp_idx < contra_idx < trends_idx < gaps_idx < concl_idx < ref_idx


def test_section_order_executive_summary():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    structured = build_doc_structured(
        output_type=OutputType.EXECUTIVE_SUMMARY,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=None,
    )

    headings = [s.heading for s in structured.sections]
    expected_order = ["Front Matter", "Purpose", "Key Findings", "Implications", "Sources"]
    assert headings == expected_order


# ---------------------------------------------------------------------------
# Distinct Structures & Content Isolation Tests
# ---------------------------------------------------------------------------

def test_three_outputs_have_distinct_structures():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    paper = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations)
    survey = build_doc_structured(OutputType.LITERATURE_SURVEY, guided, findings, citations)
    exec_sum = build_doc_structured(OutputType.EXECUTIVE_SUMMARY, guided, findings, citations)

    h_paper = [s.heading for s in paper.sections]
    h_survey = [s.heading for s in survey.sections]
    h_exec = [s.heading for s in exec_sum.sections]

    assert h_paper != h_survey
    assert h_paper != h_exec
    assert h_survey != h_exec

    # Executive summary has far fewer sections
    assert len(h_exec) == 5
    assert "Purpose" in h_exec
    assert "Purpose" not in h_paper
    assert "Purpose" not in h_survey


def test_literature_survey_contains_no_methodology():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    survey = build_doc_structured(OutputType.LITERATURE_SURVEY, guided, findings, citations)

    for section in survey.sections:
        assert "methodology" not in section.heading.lower()
        for b in section.blocks:
            if b.text:
                assert "langgraph" not in b.text.lower()
                assert "fastapi" not in b.text.lower()


def test_limitations_omitted_when_empty():
    guided_with_lim = sample_guided_input(limitations="Sample size was limited.")
    guided_empty_lim = sample_guided_input(limitations="")

    findings = sample_findings()
    citations = sample_citations("ieee")

    paper_with = build_doc_structured(OutputType.RESEARCH_PAPER, guided_with_lim, findings, citations)
    paper_without = build_doc_structured(OutputType.RESEARCH_PAPER, guided_empty_lim, findings, citations)

    headings_with = [s.heading for s in paper_with.sections]
    headings_without = [s.heading for s in paper_without.sections]

    assert "Limitations" in headings_with
    assert "Limitations" not in headings_without


# ---------------------------------------------------------------------------
# Grounding, Sanitization, Markers & Citations Tests
# ---------------------------------------------------------------------------

def test_no_arxiv_or_claim_anywhere():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    for o_type in (OutputType.RESEARCH_PAPER, OutputType.LITERATURE_SURVEY, OutputType.EXECUTIVE_SUMMARY):
        structured = build_doc_structured(o_type, guided, findings, citations)

        for sec in structured.sections:
            assert "arxiv:" not in sec.heading.lower()
            assert "claim:" not in sec.heading.lower()
            for b in sec.blocks:
                if b.text:
                    assert "arxiv:" not in b.text.lower()
                    assert "claim:" not in b.text.lower()
                for item in b.items:
                    assert "arxiv:" not in item.lower()
                    assert "claim:" not in item.lower()
                for row in b.table_rows:
                    for cell in row:
                        assert "arxiv:" not in cell.lower()
                        assert "claim:" not in cell.lower()


def test_markers_equal_inline_marker():
    guided = sample_guided_input()
    findings = sample_findings()

    # IEEE markers: [1], [2], [3]
    ieee_cit = sample_citations("ieee")
    paper_ieee = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, ieee_cit)
    all_ieee_texts = " ".join(
        b.text or " ".join(b.items)
        for s in paper_ieee.sections
        for b in s.blocks
    )
    assert "[1]" in all_ieee_texts
    assert "[2]" in all_ieee_texts

    # APA markers: (Zhang & Chen, 2023), (Adams & Baker, 2024)
    apa_cit = sample_citations("apa")
    paper_apa = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, apa_cit)
    all_apa_texts = " ".join(
        b.text or " ".join(b.items)
        for s in paper_apa.sections
        for b in s.blocks
    )
    assert "(Zhang & Chen, 2023)" in all_apa_texts or "(Adams & Baker, 2024)" in all_apa_texts


def test_references_sorted_for_apa_and_ordered_for_ieee():
    guided = sample_guided_input()
    findings = sample_findings()

    # IEEE: citation order (paper_101 was cited first -> [1], paper_202 -> [2], paper_303 -> [3])
    ieee_cit = sample_citations("ieee")
    paper_ieee = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, ieee_cit)
    ref_sec_ieee = next(s for s in paper_ieee.sections if s.heading == "References")
    ieee_entries = ref_sec_ieee.blocks[0].items
    assert len(ieee_entries) == 3
    assert ieee_entries[0].startswith("[1]")
    assert ieee_entries[1].startswith("[2]")
    assert ieee_entries[2].startswith("[3]")

    # APA: alphabetical by first author (Adams, Miller, Zhang)
    apa_cit = sample_citations("apa")
    paper_apa = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, apa_cit)
    ref_sec_apa = next(s for s in paper_apa.sections if s.heading == "References")
    apa_entries = ref_sec_apa.blocks[0].items
    assert len(apa_entries) == 3
    assert apa_entries[0].startswith("Adams, J.")
    assert apa_entries[1].startswith("Miller, S.")
    assert apa_entries[2].startswith("Zhang, W.")


def test_ungrounded_paragraphs_dropped():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    # Mock LLM returning one grounded and one ungrounded paragraph
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """{
      "abstract": "Valid abstract text.",
      "intro_motivation": "Grounded intro.",
      "intro_claim_ids": ["claim_001"],
      "related_work_themes": [
        {
          "title": "Grounding Test Theme",
          "paragraphs": [
            {"text": "This paragraph has a verified claim.", "claim_ids": ["claim_001"]},
            {"text": "This paragraph has a fake hallucinated claim.", "claim_ids": ["fake_claim_999"]}
          ]
        }
      ],
      "results_comparison": [],
      "conclusion": "Conclusion.",
      "diagram_nodes": [],
      "diagram_edges": []
    }"""

    paper = build_doc_structured(
        OutputType.RESEARCH_PAPER, guided, findings, citations, llm=mock_llm
    )

    theme_sec = next(s for s in paper.sections if "Grounding Test Theme" in s.heading)
    theme_texts = [b.text for b in theme_sec.blocks if b.text]

    assert len(theme_texts) == 1
    assert "verified claim" in theme_texts[0]
    assert "fake hallucinated claim" not in " ".join(theme_texts)


def test_results_table_numbers_must_appear_in_key_results():
    key_results = "Latency dropped by 35% and throughput reached 42 req/s."

    # Valid table: every number (35%, 42) appears in key_results
    valid_tbl = ContentBlock(
        kind="table",
        table_header=["Metric", "Value"],
        table_rows=[["Latency reduction", "35%"], ["Throughput", "42"]],
    )
    assert validate_results_table(valid_tbl, key_results) is True

    # Invalid table: contains 99% which does NOT appear in key_results
    invalid_tbl = ContentBlock(
        kind="table",
        table_header=["Metric", "Value"],
        table_rows=[["Accuracy", "99%"], ["Throughput", "42"]],
    )
    assert validate_results_table(invalid_tbl, key_results) is False


# ---------------------------------------------------------------------------
# Fallback & Single LLM Call Tests
# ---------------------------------------------------------------------------

def test_fallback_on_llm_failure():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("API quota exhausted or network error")

    structured = build_doc_structured(
        OutputType.RESEARCH_PAPER, guided, findings, citations, llm=mock_llm
    )

    assert structured is not None
    assert len(structured.sections) >= 7
    headings = [s.heading for s in structured.sections]
    assert "Front Matter" in headings
    assert "Introduction" in headings
    assert "References" in headings


def test_fallback_on_invalid_json():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Sorry, as an AI I cannot {invalid json"

    structured = build_doc_structured(
        OutputType.LITERATURE_SURVEY, guided, findings, citations, llm=mock_llm
    )

    assert structured is not None
    headings = [s.heading for s in structured.sections]
    assert "Taxonomy of Surveyed Literature" in headings
    assert "References" in headings


def test_one_llm_call_per_document():
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "{}"

    build_doc_structured(OutputType.EXECUTIVE_SUMMARY, guided, findings, citations, llm=mock_llm)

    assert mock_llm.generate.call_count == 1
    _, kwargs = mock_llm.generate.call_args
    assert kwargs.get("agent_name") == "composer"
    assert kwargs.get("paper_id") == "__compose__"
    assert kwargs.get("purpose") == "doc_executive_summary"


# ---------------------------------------------------------------------------
# Integration Test: Real DOCX Renderer
# ---------------------------------------------------------------------------

def test_integration_render_docx_real_renderer(tmp_path: Path):
    guided = sample_guided_input()
    findings = sample_findings()
    citations = sample_citations("ieee")

    # 1. Research Paper DOCX
    paper_structured = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations)
    paper_res = ComposerResult(
        output_type=OutputType.RESEARCH_PAPER,
        title=guided.cover_info.title,
        content="Fallback markdown",
        structured=paper_structured,
    )
    paper_path = tmp_path / "research_paper.docx"
    render_docx(paper_res, paper_path)

    assert paper_path.exists()
    doc_paper = Document(paper_path)
    # Assert A4 dimensions
    first_sec = doc_paper.sections[0]
    assert round(first_sec.page_width.cm, 1) == 21.0
    assert round(first_sec.page_height.cm, 1) == 29.7
    # Assert at least one two-column section
    has_two_col = any(
        s._sectPr.find(qn("w:cols")) is not None
        and s._sectPr.find(qn("w:cols")).get(qn("w:num")) == "2"
        for s in doc_paper.sections
    )
    assert has_two_col is True
    # Assert at least one table rendered
    assert len(doc_paper.tables) >= 1

    # 2. Executive Summary DOCX
    exec_structured = build_doc_structured(OutputType.EXECUTIVE_SUMMARY, guided, findings, citations)
    exec_res = ComposerResult(
        output_type=OutputType.EXECUTIVE_SUMMARY,
        title=guided.cover_info.title,
        content="Fallback markdown",
        structured=exec_structured,
    )
    exec_path = tmp_path / "executive_summary.docx"
    render_docx(exec_res, exec_path)

    assert exec_path.exists()
    doc_exec = Document(exec_path)
    # Assert A4 dimensions
    assert round(doc_exec.sections[0].page_width.cm, 1) == 21.0
    assert round(doc_exec.sections[0].page_height.cm, 1) == 29.7
    # Assert all sections in Executive Summary are single-column
    for s in doc_exec.sections:
        cols = s._sectPr.find(qn("w:cols"))
        if cols is not None:
            assert cols.get(qn("w:num")) in (None, "1")


# ---------------------------------------------------------------------------
# Specific Bugfix Tests for Polish Requirements
# ---------------------------------------------------------------------------

def test_extract_complete_short_clause():
    """Verify that extract_complete_short_clause never uses '...' and never cuts mid-sentence."""
    # 1. Normal short sentence <= 30 words
    s1 = "We propose an end-to-end multi-agent framework for automated literature review and synthesis."
    res1 = extract_complete_short_clause(s1, max_words=30)
    assert res1 == s1
    assert "..." not in res1
    assert res1.endswith(".")

    # 2. Sentence with clause break (; or conjunction)
    s2 = "Our architecture achieves a 35% reduction in latency compared to baselines; this improvement is maintained under extreme concurrent loads without memory degradation."
    res2 = extract_complete_short_clause(s2, max_words=20)
    assert "..." not in res2
    assert res2.endswith(".")
    assert len(res2.split()) <= 20
    assert "Our architecture achieves a 35% reduction in latency compared to baselines." == res2

    # 3. Empty or hyphen
    assert extract_complete_short_clause("") == "-"
    assert extract_complete_short_clause(None) == "-"
    assert extract_complete_short_clause("-") == "-"


def test_no_ellipsis_in_any_table_cell():
    """Verify that no table cell across research paper and literature survey contains '...'."""
    guided = sample_guided_input()
    findings = sample_findings(with_contradictions=True)
    citations = sample_citations("ieee")

    for o_type in (OutputType.RESEARCH_PAPER, OutputType.LITERATURE_SURVEY):
        structured = build_doc_structured(o_type, guided, findings, citations)

        for sec in structured.sections:
            for b in sec.blocks:
                if b.kind == "table":
                    for row in b.table_rows:
                        for cell in row:
                            cell_str = str(cell)
                            assert "..." not in cell_str, f"Found '...' in table cell: {cell_str}"
                            assert not cell_str.endswith("..."), f"Table cell ends with '...': {cell_str}"


def test_contributions_no_implementation_of_we():
    """Verify contributions restate user text as grammatical full sentences without glued templates."""
    guided = sample_guided_input()
    # Provide the exact triggering texts mentioned in the problem description
    guided.academic_content_info.methodology = "We reviewed recent literature and developed a flight simulator."
    guided.academic_content_info.what_was_measured = "Total revenue per flight was assessed across quarters."
    guided.academic_content_info.key_results = "Turnaround time was reduced by 22%."

    findings = sample_findings()
    citations = sample_citations("ieee")

    structured = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations)

    intro_sec = next(s for s in structured.sections if s.heading == "Introduction")
    bullet_blocks = [b for b in intro_sec.blocks if b.kind == "bullets"]
    assert len(bullet_blocks) >= 1
    contrib_items = bullet_blocks[0].items

    assert len(contrib_items) >= 2
    for item in contrib_items:
        assert not item.startswith("Implementation of We"), f"Found glued template in: {item}"
        assert not item.startswith("Implementation of"), f"Found glued template in: {item}"
        assert not item.startswith("Empirical evaluation of"), f"Found glued template in: {item}"
        assert item[0].isupper(), f"Contribution not capitalized: {item}"
        assert item.endswith((".", "!", "?")), f"Contribution not ending with punctuation: {item}"

    # Also test deterministic fallback path explicitly
    mock_failing_llm = MagicMock()
    mock_failing_llm.generate.side_effect = RuntimeError("Fallback test")
    fallback_struct = build_doc_structured(
        OutputType.RESEARCH_PAPER, guided, findings, citations, llm=mock_failing_llm
    )
    fallback_intro = next(s for s in fallback_struct.sections if s.heading == "Introduction")
    fallback_bullets = [b for b in fallback_intro.blocks if b.kind == "bullets"][0].items

    assert len(fallback_bullets) >= 2
    for item in fallback_bullets:
        assert not item.startswith("Implementation of We")
        assert not item.startswith("Implementation of")
        assert not item.startswith("Empirical evaluation of")
        assert item[0].isupper()
        assert item.endswith((".", "!", "?"))

    assert "We reviewed recent literature and developed a flight simulator." in fallback_bullets
    assert "Total revenue per flight was assessed across quarters." in fallback_bullets


def test_methodology_subsections_and_tools_sentence():
    """Verify Methodology uses '## ' subsections and implementation tools are written as ONE sentence."""
    guided = sample_guided_input()
    guided.academic_content_info.tools_used = ["Python", "pandas", "scikit-learn"]

    findings = sample_findings()
    citations = sample_citations("ieee")

    structured = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations)

    headings = [s.heading for s in structured.sections]
    assert "Methodology" in headings
    assert "## Dataset" in headings
    assert "## Implementation" in headings
    assert "## Evaluation Metrics" in headings

    # Verify no run-in labels in block text
    for sec in structured.sections:
        for b in sec.blocks:
            if b.text:
                assert not b.text.startswith("Dataset & Sample Specification:"), f"Found run-in label: {b.text}"
                assert not b.text.startswith("Evaluation Metrics & Measured Parameters:"), f"Found run-in label: {b.text}"
                assert not b.text.startswith("Implementation Tools and Software Stack:"), f"Found run-in label: {b.text}"

    # Verify implementation tools sentence
    impl_sec = next(s for s in structured.sections if s.heading == "## Implementation")
    para_blocks = [b for b in impl_sec.blocks if b.kind == "paragraph"]
    assert len(para_blocks) >= 1
    tools_para = para_blocks[0].text
    assert tools_para == "The implementation uses Python, pandas, and scikit-learn."


def test_roadmap_matches_actual_headings():
    """Verify roadmap sentence dynamically matches the actual section headings and numbers."""
    guided = sample_guided_input()
    findings_with_contra = sample_findings(with_contradictions=True)
    findings_no_contra = sample_findings(with_contradictions=False)
    citations = sample_citations("ieee")

    # 1. Research paper roadmap
    paper_struct = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings_with_contra, citations)
    intro_sec = next(s for s in paper_struct.sections if s.heading == "Introduction")
    roadmap_p = [b.text for b in intro_sec.blocks if b.kind == "paragraph" and "organized as follows" in b.text][0]

    if "Section 3 details problem formulation" in roadmap_p:
        assert "Section 2 reviews related literature" in roadmap_p
        assert "Section 3 details problem formulation" in roadmap_p
        assert "Section 4 outlines the proposed methodology and experimental setup" in roadmap_p
        assert "Section 5 presents empirical results" in roadmap_p
        assert "Section 6 discusses findings and implications" in roadmap_p
        assert "Section 7 concludes the paper" in roadmap_p
    else:
        assert "Section 2 reviews related literature" in roadmap_p
        assert "Section 3 outlines the proposed methodology and experimental setup" in roadmap_p
        assert "Section 4 analyzes empirical results and discussion" in roadmap_p
        assert "Section 5 concludes the paper" in roadmap_p

    # 2. Literature survey roadmap WITH contradictions
    survey_contra = build_doc_structured(OutputType.LITERATURE_SURVEY, guided, findings_with_contra, citations)
    intro_survey = next(s for s in survey_contra.sections if s.heading == "Introduction")
    roadmap_survey_1 = [b.text for b in intro_survey.blocks if b.kind == "paragraph" and "organized as follows" in b.text][0]

    assert "Section 2 presents the taxonomy of surveyed literature" in roadmap_survey_1
    assert "Section 3 provides a consolidated summary of reviewed studies" in roadmap_survey_1
    assert "Section 4 delivers a comparative analysis across studies" in roadmap_survey_1
    assert "Section 5 examines conflicting and open findings" in roadmap_survey_1
    assert "Section 6 explores emerging trends" in roadmap_survey_1
    assert "Section 7 identifies research gaps and future directions" in roadmap_survey_1
    assert "Section 8 concludes the survey" in roadmap_survey_1

    # 3. Literature survey roadmap WITHOUT contradictions (Conflicting section omitted, numbers shift)
    survey_no_contra = build_doc_structured(OutputType.LITERATURE_SURVEY, guided, findings_no_contra, citations)
    intro_survey_2 = next(s for s in survey_no_contra.sections if s.heading == "Introduction")
    roadmap_survey_2 = [b.text for b in intro_survey_2.blocks if b.kind == "paragraph" and "organized as follows" in b.text][0]

    assert "conflicting and open findings" not in roadmap_survey_2.lower()
    assert "Section 5 explores emerging trends" in roadmap_survey_2
    assert "Section 6 identifies research gaps and future directions" in roadmap_survey_2
    assert "Section 7 concludes the survey" in roadmap_survey_2


# ---------------------------------------------------------------------------
# Task F: Extended Depth, 8x8 Claims, Section Omission, Fallback & Call Count
# ---------------------------------------------------------------------------

def make_8x8_evidence():
    summaries = []
    claims = []
    citations = []

    for i in range(1, 9):
        pid = f"paper_{i}"
        summaries.append(
            PaperSummary(
                paper_id=pid,
                title=f"Theoretical and Empirical Optimization in Architecture {i}",
                authors=[f"Researcher, Alpha {i}", f"Scientist, Beta {i}"],
                year=2018 + i,
                venue="NeurIPS" if i % 2 == 0 else "ICML",
                summary=f"Investigates systematic trade-offs in distributed representation learning and inference scaling for component {i}.",
            )
        )
        citations.append(
            FormattedCitation(
                citation_id=f"cit_{i}",
                paper_id=pid,
                citation_style="ieee",
                inline_marker=f"[{i}]",
                full_entry=f'[{i}] A. Researcher and B. Scientist, "Theoretical and Empirical Optimization in Architecture {i}," NeurIPS, {2018 + i}.',
            )
        )
        for j in range(1, 9):
            cid = f"claim_{i}_{j}"
            claims.append(
                Claim(
                    claim_id=cid,
                    text=f"Benchmark trial {j} for system architecture {i} achieves an empirical gain of {10 * i + j}% over baseline configurations.",
                    source_paper_id=pid,
                    verification_status="verified",
                )
            )

    findings = FindingsPacket(
        topic="Scalable Multi-Agent Research Architectures",
        summaries=summaries,
        claims=claims,
        contradiction_details=[
            ContradictionDetail(
                claim_a_id="claim_1_1",
                claim_b_id="claim_2_1",
                paper_a_id="paper_1",
                paper_b_id="paper_2",
                explanation="Paper 1 demonstrates latency advantages under sparse indexing while Paper 2 observes memory saturation under dense indexing.",
                shared_subject="Sparse vs dense indexing trade-offs",
            )
        ],
    )
    citation_res = CitationResult(
        citation_style="ieee",
        citations=citations,
        bibliography=[],
    )
    return findings, citation_res


def count_doc_words(structured) -> int:
    total = 0
    for sec in structured.sections:
        for b in sec.blocks:
            if b.text:
                total += len(b.text.split())
            if b.items:
                for it in b.items:
                    total += len(it.split())
            if b.table_rows:
                for row in b.table_rows:
                    for cell in row:
                        total += len(str(cell).split())
    return total


def test_research_paper_extended_depth_8x8_word_count(monkeypatch):
    """With 8 papers x 8 verified claims, research paper has >= 2500 words and strictly respects grounding."""
    monkeypatch.setenv("DOC_DEPTH", "extended")
    guided = sample_guided_input()
    findings, citations = make_8x8_evidence()

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "{}"

    structured = build_doc_structured(
        output_type=OutputType.RESEARCH_PAPER,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=mock_llm,
    )

    total_words = count_doc_words(structured)
    assert total_words >= 2500, f"Expected >= 2500 words, got {total_words}"

    all_texts = []
    valid_cids = {c.claim_id for c in findings.claims if c.verification_status == "verified"}

    for s in structured.sections:
        assert "arxiv:" not in s.heading.lower()
        assert "claim:" not in s.heading.lower()
        for b in s.blocks:
            if b.text:
                all_texts.append(b.text)
                assert "arxiv:" not in b.text.lower()
                assert "claim:" not in b.text.lower()
            if b.items:
                for it in b.items:
                    all_texts.append(it)
                    assert "arxiv:" not in it.lower()
                    assert "claim:" not in it.lower()
            if b.table_rows:
                for row in b.table_rows:
                    for cell in row:
                        c_str = str(cell)
                        assert "arxiv:" not in c_str.lower()
                        assert "claim:" not in c_str.lower()
            for cid in b.claim_ids:
                assert cid in valid_cids, f"Found unverified claim ID: {cid}"

    combined_corpus = " ".join(all_texts)
    # Deterministic markers [1] through [8] must all be present
    for i in range(1, 9):
        assert f"[{i}]" in combined_corpus, f"Marker [{i}] missing from text"


def test_sections_omitted_when_no_source_text(monkeypatch):
    """With minimal evidence, sections with no source text are omitted rather than padded."""
    monkeypatch.setenv("DOC_DEPTH", "extended")
    minimal_guided = GuidedInputBundle(
        cover_info=CoverInfo(
            title="Minimal Empirical Study",
            authors=["Alice Minimal"],
            institution="Research Lab",
            date="October 2026",
        ),
        academic_content_info=AcademicContentInfo(
            methodology="",
            dataset_or_sample="",
            tools_used=[],
            what_was_measured="",
            key_results="Observed metric of 42.0%.",
            limitations="",
        ),
        project_presentation_info=ProjectPresentationInfo(
            problem_statement="",
            tech_stack=[],
            own_architecture_summary="",
            own_results_summary="",
        ),
    )
    findings, citations = make_8x8_evidence()
    findings.contradiction_details = []  # No contradictions

    structured = build_doc_structured(
        output_type=OutputType.RESEARCH_PAPER,
        guided_input=minimal_guided,
        findings=findings,
        citation_result=citations,
        llm=None,
    )

    headings = [s.heading for s in structured.sections]

    # Verify omission
    assert "Problem Formulation" not in headings
    assert "Methodology" not in headings
    assert "## Architecture" not in headings
    assert "## Dataset" not in headings
    assert "## Implementation" not in headings
    assert "## Evaluation Metrics" not in headings
    assert "## Threats to Validity" not in headings
    assert "Limitations" not in headings
    assert "## Conflicting and Open Findings" not in headings

    # Verify no padding filler text
    for s in structured.sections:
        for b in s.blocks:
            if b.text:
                assert "representative benchmark datasets" not in b.text
                assert "open-source research frameworks" not in b.text


def test_per_section_fallback_on_partial_failure(monkeypatch):
    """When an individual section LLM call fails, that section falls back deterministically without breaking the document."""
    monkeypatch.setenv("DOC_DEPTH", "extended")
    guided = sample_guided_input()
    findings = sample_findings(with_contradictions=True)
    citations = sample_citations("ieee")

    call_index = 0

    def mock_generate_side_effect(prompt, **kwargs):
        nonlocal call_index
        call_index += 1
        if call_index == 2:
            raise RuntimeError("Simulated transient network timeout on section 2")
        return "{}"

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = mock_generate_side_effect

    structured = build_doc_structured(
        output_type=OutputType.RESEARCH_PAPER,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=mock_llm,
    )

    assert structured is not None
    headings = [s.heading for s in structured.sections]
    assert "Front Matter" in headings
    assert "Abstract" in headings
    assert "Introduction" in headings
    assert "Related Work" in headings
    assert "References" in headings


def test_llm_call_count_le_10(monkeypatch):
    """Ensure total LLM calls per document never exceed 10."""
    monkeypatch.setenv("DOC_DEPTH", "extended")
    guided = sample_guided_input()
    findings, citations = make_8x8_evidence()

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "{}"

    build_doc_structured(
        output_type=OutputType.RESEARCH_PAPER,
        guided_input=guided,
        findings=findings,
        citation_result=citations,
        llm=mock_llm,
    )

    assert mock_llm.generate.call_count <= 10, f"Expected <= 10 calls, got {mock_llm.generate.call_count}"


def test_doc_depth_setting_standard_vs_extended(monkeypatch):
    """Verify DOC_DEPTH setting switches between standard and extended behavior."""
    guided = sample_guided_input()
    findings = sample_findings(with_contradictions=True)
    citations = sample_citations("ieee")

    # 1. Standard depth
    monkeypatch.setenv("DOC_DEPTH", "standard")
    doc_std = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations, llm=None)
    headings_std = [s.heading for s in doc_std.sections]
    assert "Results and Discussion" in headings_std
    assert "Conclusion" in headings_std
    assert "Problem Formulation" not in headings_std

    # 2. Extended depth
    monkeypatch.setenv("DOC_DEPTH", "extended")
    doc_ext = build_doc_structured(OutputType.RESEARCH_PAPER, guided, findings, citations, llm=None)
    headings_ext = [s.heading for s in doc_ext.sections]
    assert "Results" in headings_ext
    assert "Discussion" in headings_ext
    assert "Conclusion and Future Work" in headings_ext
    assert "Problem Formulation" in headings_ext

