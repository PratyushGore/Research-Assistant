import logging
from pathlib import Path
import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Cm

from backend.agents.output_renderer.docx_renderer import render_docx
from backend.agents.output_renderer import theme
from backend.schemas.schemas import (
    ComposerResult,
    ContentBlock,
    DocSection,
    FigureSpec,
    OutputType,
    StructuredContent,
)


def sample_composer_result() -> ComposerResult:
    """Fallback unstructured composer result for backward-compatibility testing."""
    return ComposerResult(
        output_type=OutputType.LITERATURE_SURVEY,
        title="AI Research Assistant",
        content=(
            "## Abstract\nThis is the abstract.\n\n"
            "## Introduction\nThis is the introduction."
        ),
        sections={
            "Abstract": "This is the abstract.",
            "Introduction": "This is the introduction.",
            "References": "1. Smith, John. (2025). AI Research.",
        },
        citations_used=["citation-paper-001"],
    )


def build_research_paper_composer_result() -> ComposerResult:
    """Construct a full structured ComposerResult for a Research Paper covering all block kinds."""
    return ComposerResult(
        output_type=OutputType.RESEARCH_PAPER,
        title="Scalable Multi-Agent Research Architectures",
        content="Markdown fallback content",
        structured=StructuredContent(
            sections=[
                DocSection(
                    heading="Front Matter",
                    blocks=[
                        ContentBlock(kind="paragraph", text="Scalable Multi-Agent Research Architectures"),
                        ContentBlock(kind="paragraph", text="Dr. A. Vaswani, AI Research Lab"),
                        ContentBlock(kind="paragraph", text="vaswani@example.org — October 2026"),
                    ],
                ),
                DocSection(
                    heading="Abstract",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="This paper investigates decoupled multi-agent architectures for academic research synthesis.",
                        ),
                    ],
                ),
                DocSection(
                    heading="Introduction",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="Manual literature review is labor-intensive and prone to hallucinated references.",
                        ),
                        ContentBlock(
                            kind="paragraph",
                            text="Second paragraph of introduction testing the first-line indent requirement.",
                        ),
                        ContentBlock(
                            kind="bullets",
                            items=[
                                "Monolithic LLM chains suffer from context bottleneck and factual drift.",
                                "Decoupled specialist agents achieve higher retrieval precision and verified provenance.",
                            ],
                        ),
                        ContentBlock(
                            kind="callout",
                            text="Core Hypothesis: Specialized verification agents reduce citation hallucinations to 0.0%.",
                        ),
                    ],
                ),
                DocSection(
                    heading="Empirical Evaluation",
                    blocks=[
                        ContentBlock(
                            kind="key_numbers",
                            items=["35% :: Latency Drop", "99.4% :: Recall Rate", "0.0% :: Hallucinations"],
                        ),
                        ContentBlock(
                            kind="table",
                            table_header=["Architecture", "Throughput", "F1 Score", "Status"],
                            table_rows=[
                                ["Baseline Monolith", "14 req/s", "0.81", "Legacy"],
                                ["Agentic Workflow", "42 req/s", "0.97", "Verified"],
                            ],
                            caption="System Performance Across Benchmark Datasets",
                        ),
                        ContentBlock(
                            kind="figure",
                            figure_id="fig_chart_throughput",
                            caption="Throughput Comparison Across Architectures",
                        ),
                    ],
                ),
                DocSection(
                    heading="Limitations",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="This study focuses exclusively on English-language academic corpora.",
                        ),
                    ],
                ),
                DocSection(
                    heading="Acknowledgments",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="We thank the academic review committee for their thoughtful feedback.",
                        ),
                    ],
                ),
                DocSection(
                    heading="References",
                    blocks=[
                        ContentBlock(
                            kind="bullets",
                            items=[
                                "Vaswani, A., Shazeer, N., et al. (2017). Attention is all you need. NeurIPS.",
                                "Devlin, J., Chang, M. W., et al. (2018). BERT: Pre-training of deep bidirectional transformers. NAACL.",
                            ],
                        ),
                    ],
                ),
            ],
            figures=[
                FigureSpec(
                    figure_id="fig_chart_throughput",
                    kind="bar_chart",
                    title="Evaluation Throughput",
                    labels=["Baseline Monolith", "Agentic Workflow"],
                    values=[14.0, 42.0],
                ),
            ],
        ),
    )


def build_literature_survey_composer_result() -> ComposerResult:
    """Construct a full structured ComposerResult for a Literature Survey."""
    return ComposerResult(
        output_type=OutputType.LITERATURE_SURVEY,
        title="Comprehensive Survey on Retrieval-Augmented Generation",
        content="Markdown fallback content",
        structured=StructuredContent(
            sections=[
                DocSection(
                    heading="Front Matter",
                    blocks=[
                        ContentBlock(kind="paragraph", text="Comprehensive Survey on Retrieval-Augmented Generation"),
                        ContentBlock(kind="paragraph", text="Advances in Vector Retrieval and Multi-Agent Synthesis"),
                        ContentBlock(kind="paragraph", text="Research Assistant Team — 2026"),
                    ],
                ),
                DocSection(
                    heading="Abstract",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="We survey 250 peer-reviewed papers on dense retrieval and factual verification.",
                        ),
                    ],
                ),
                DocSection(
                    heading="Overview & Taxonomy",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="Retrieval-augmented generation has evolved from simple dense lookups to orchestrated multi-hop verification.",
                        ),
                        ContentBlock(
                            kind="table",
                            table_header=["Paradigm", "Key Mechanism", "Limitation"],
                            table_rows=[
                                ["Sparse Retrieval", "Lexical BM25 Matching", "Vocabulary Mismatch"],
                                ["Dense Retrieval", "Bi-Encoder Embeddings", "Higher Compute Cost"],
                            ],
                            caption="Taxonomy of Information Retrieval Paradigms",
                        ),
                    ],
                ),
                DocSection(
                    heading="Architectural Paradigms",
                    blocks=[
                        ContentBlock(
                            kind="figure",
                            figure_id="fig_diag_workflow",
                            caption="End-to-End Orchestration Architecture Flow",
                        ),
                    ],
                ),
                DocSection(
                    heading="References",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS.\nKarpukhin, V. et al. (2020). Dense Passage Retrieval for Open-Domain Question Answering. EMNLP.",
                        ),
                    ],
                ),
            ],
            figures=[
                FigureSpec(
                    figure_id="fig_diag_workflow",
                    kind="diagram",
                    title="Orchestration Architecture",
                    nodes=["Query Parser", "Vector Retriever", "Fact Verifier"],
                    edges=[("Query Parser", "Vector Retriever"), ("Vector Retriever", "Fact Verifier")],
                ),
            ],
        ),
    )


def build_executive_summary_composer_result() -> ComposerResult:
    """Construct a full structured ComposerResult for an Executive Summary."""
    return ComposerResult(
        output_type=OutputType.EXECUTIVE_SUMMARY,
        title="Executive Briefing: Enterprise AI Integration",
        content="Markdown fallback content",
        structured=StructuredContent(
            sections=[
                DocSection(
                    heading="Front Matter",
                    blocks=[
                        ContentBlock(kind="paragraph", text="Executive Briefing: Enterprise AI Integration"),
                        ContentBlock(kind="paragraph", text="Strategic Assessment and ROI Projection for Autonomous Literature Systems"),
                        ContentBlock(kind="paragraph", text="Prepared by AI Strategy Group — Q4 2026"),
                    ],
                ),
                DocSection(
                    heading="Executive Summary",
                    blocks=[
                        ContentBlock(
                            kind="paragraph",
                            text="Deploying autonomous literature assistants accelerates organizational R&D cycles while eliminating citation errors.",
                        ),
                        ContentBlock(
                            kind="key_numbers",
                            items=["3.4x :: Efficiency Boost", "$1.2M :: Estimated Savings", "14 Days :: Rollout Time"],
                        ),
                    ],
                ),
                DocSection(
                    heading="Strategic Recommendations",
                    blocks=[
                        ContentBlock(
                            kind="bullets",
                            items=[
                                "Standardize on modular agent microservices with centralized telemetry.",
                                "Establish automated fact-verification gating prior to document export.",
                            ],
                        ),
                        ContentBlock(
                            kind="callout",
                            text="Recommendation: Initiate 30-day proof-of-concept pilot with engineering and legal compliance teams.",
                        ),
                        ContentBlock(
                            kind="table",
                            table_header=["Phase", "Milestone", "Target Timeline"],
                            table_rows=[
                                ["Phase 1: Pilot", "Core pipeline validation", "Month 1"],
                                ["Phase 2: Scale", "Enterprise-wide rollout", "Month 3"],
                            ],
                            caption="Strategic Implementation Timeline",
                        ),
                    ],
                ),
            ],
            figures=[],
        ),
    )


# ---------------------------------------------------------------------------
# Existing Fallback Tests (Must Remain Passing)
# ---------------------------------------------------------------------------

def test_render_docx_creates_file(tmp_path: Path):
    output_path = tmp_path / "literature_survey.docx"

    result = render_docx(
        sample_composer_result(),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.is_file()


def test_render_docx_contains_title_and_sections(tmp_path: Path):
    output_path = tmp_path / "research_output.docx"

    render_docx(
        sample_composer_result(),
        output_path,
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert "AI Research Assistant" in text
    assert "Abstract" in text
    assert "This is the abstract." in text
    assert "Introduction" in text
    assert "This is the introduction." in text
    assert "References" in text


def test_render_docx_preserves_section_order(tmp_path: Path):
    output_path = tmp_path / "ordered.docx"

    render_docx(
        sample_composer_result(),
        output_path,
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert text.index("Abstract") < text.index("Introduction")
    assert text.index("Introduction") < text.index("References")


def test_render_docx_creates_parent_directory(tmp_path: Path):
    output_path = tmp_path / "generated" / "nested" / "output.docx"

    render_docx(
        sample_composer_result(),
        output_path,
    )

    assert output_path.exists()


def test_render_docx_rejects_non_docx_path(tmp_path: Path):
    output_path = tmp_path / "output.pdf"

    try:
        render_docx(
            sample_composer_result(),
            output_path,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Output path must have a .docx extension" in str(exc)


# ---------------------------------------------------------------------------
# Comprehensive Structured Tests for All Output Types and Block Kinds
# ---------------------------------------------------------------------------

def test_render_docx_all_three_output_types_to_temp_dir(tmp_path: Path):
    """
    Render hand-made ComposerResults for all three output types covering every block kind,
    print their paths, and assert publication-grade formatting properties.
    """
    path_rp = tmp_path / "research_paper.docx"
    path_ls = tmp_path / "literature_survey.docx"
    path_es = tmp_path / "executive_summary.docx"

    render_docx(build_research_paper_composer_result(), path_rp)
    render_docx(build_literature_survey_composer_result(), path_ls)
    render_docx(build_executive_summary_composer_result(), path_es)

    # Print output paths as requested
    print(f"\nRendered Sample Research Paper: {path_rp.resolve()}")
    print(f"Rendered Sample Literature Survey: {path_ls.resolve()}")
    print(f"Rendered Sample Executive Summary: {path_es.resolve()}")

    assert path_rp.exists()
    assert path_ls.exists()
    assert path_es.exists()

    # -----------------------------------------------------------------------
    # 1. Assertions on Research Paper (Academic Layout)
    # -----------------------------------------------------------------------
    doc_rp = Document(path_rp)
    para_rp = doc_rp.paragraphs

    # A. Page size is A4 & margins 2.5 cm
    sec_0 = doc_rp.sections[0]
    assert round(sec_0.page_width.cm, 1) == 21.0
    assert round(sec_0.page_height.cm, 1) == 29.7
    assert round(sec_0.left_margin.cm, 1) == 2.5
    assert round(sec_0.right_margin.cm, 1) == 2.5
    assert round(sec_0.top_margin.cm, 1) == 2.5
    assert round(sec_0.bottom_margin.cm, 1) == 2.5

    # B. Academic body section has w:cols num=2 and title/abstract section has 1 column
    cols_0 = sec_0._sectPr.find(qn("w:cols"))
    assert cols_0 is None or cols_0.get(qn("w:num")) in (None, "1")

    sec_1 = doc_rp.sections[1]
    cols_1 = sec_1._sectPr.find(qn("w:cols"))
    assert cols_1 is not None and cols_1.get(qn("w:num")) == "2"

    # C. Abstract paragraph indents are set (narrow centered block)
    abstract_paras = [
        p for p in para_rp
        if "This paper investigates decoupled multi-agent architectures" in p.text
    ]
    assert len(abstract_paras) == 1
    ab_p = abstract_paras[0]
    assert ab_p.paragraph_format.left_indent is not None
    assert ab_p.paragraph_format.left_indent.cm >= 3.5
    assert ab_p.paragraph_format.right_indent is not None
    assert ab_p.paragraph_format.right_indent.cm >= 3.5

    # D. Headings numbered correctly and Abstract/Limitations/Acknowledgments/References unnumbered
    # Numbering style: '1 Introduction', '2 Empirical Evaluation' (number + space, no period)
    headings_rp = [p.text for p in para_rp if p.style.name.startswith("Heading")]
    assert "Abstract" in headings_rp
    assert "1 Introduction" in headings_rp
    assert "2 Empirical Evaluation" in headings_rp
    assert "Limitations" in headings_rp
    assert "Acknowledgments" in headings_rp
    assert "References" in headings_rp
    # Assert no period in numbering
    assert not any(h.startswith("1.") or h.startswith("2.") for h in headings_rp)
    # Front Matter heading not printed
    assert all(p.text != "Front Matter" for p in para_rp)

    # E. Table caption paragraph comes BEFORE the table and figure caption comes AFTER the figure content
    body_elements = doc_rp._body._body.getchildren()
    elem_tags = [c.tag.split("}")[-1] for c in body_elements]

    # Find native table and its caption
    table_caption_indices = [
        i for i, c in enumerate(body_elements)
        if c.tag.endswith("p") and "Table 1:" in c.text
    ]
    assert len(table_caption_indices) == 1
    tc_idx = table_caption_indices[0]
    # The element following the table caption must be a table (<w:tbl>)
    assert elem_tags[tc_idx + 1] == "tbl"

    # Find figure table and its caption
    fig_caption_indices = [
        i for i, c in enumerate(body_elements)
        if c.tag.endswith("p") and "Figure 1:" in c.text
    ]
    assert len(fig_caption_indices) == 1
    fc_idx = fig_caption_indices[0]
    # The element preceding the figure caption must be a table (<w:tbl>) representing the figure
    assert elem_tags[fc_idx - 1] == "tbl"

    # F. Tables have top/bottom borders and no vertical borders in academic mode
    native_tbl = doc_rp.tables[0]  # First table is the empirical evaluation table
    tblBorders = native_tbl._tbl.tblPr.find(qn("w:tblBorders"))
    assert tblBorders is not None
    assert tblBorders.find(qn("w:top")).get(qn("w:val")) == "single"
    assert tblBorders.find(qn("w:bottom")).get(qn("w:val")) == "single"
    assert tblBorders.find(qn("w:left")).get(qn("w:val")) == "none"
    assert tblBorders.find(qn("w:right")).get(qn("w:val")) == "none"
    assert tblBorders.find(qn("w:insideV")).get(qn("w:val")) == "none"
    # No fills on cells in academic mode
    for row in native_tbl.rows:
        for cell in row.cells:
            assert cell._tc.find(qn("w:shd")) is None

    # G. A wide figure/table is surrounded by single-column continuous section breaks
    # In doc_rp, Empirical Evaluation table has 4 columns (wide table).
    # It must be preceded by a continuous section with 1 column and followed by 2 columns.
    sec_col_counts = []
    for s in doc_rp.sections:
        c = s._sectPr.find(qn("w:cols"))
        val = c.get(qn("w:num")) if c is not None else "1"
        sec_col_counts.append(val or "1")
    # Section sequence: 1 (title/abstract) -> 2 (body) -> 1 (wide table) -> 2 (body reopened)
    assert "1" in sec_col_counts
    assert "2" in sec_col_counts
    assert len(sec_col_counts) >= 4

    # H. Footer has a PAGE field
    footer_xml = sec_0.footer.paragraphs[0]._p.xml
    assert 'w:instr="PAGE"' in footer_xml

    # I. References have hanging indent and are not justified
    ref_paras = [p for p in para_rp if p.style.name == "References"]
    assert len(ref_paras) >= 2
    for rp in ref_paras:
        assert rp.paragraph_format.left_indent is not None
        assert rp.paragraph_format.left_indent.cm >= 0.4
        assert rp.paragraph_format.first_line_indent is not None
        assert rp.paragraph_format.first_line_indent.cm <= -0.4
        assert rp.alignment == WD_ALIGN_PARAGRAPH.LEFT
        assert rp.alignment != WD_ALIGN_PARAGRAPH.JUSTIFY

    # J. First paragraph after heading has 0 first line indent; subsequent has 0.4 cm
    p_intro_1 = [p for p in para_rp if "Manual literature review is labor-intensive" in p.text][0]
    p_intro_2 = [p for p in para_rp if "Second paragraph of introduction" in p.text][0]
    assert p_intro_1.paragraph_format.first_line_indent.pt == 0
    assert round(p_intro_2.paragraph_format.first_line_indent.cm, 1) == 0.4

    # -----------------------------------------------------------------------
    # 2. Assertions on Literature Survey (Wide Diagram Figure)
    # -----------------------------------------------------------------------
    doc_ls = Document(path_ls)
    # The diagram figure spans both columns -> surrounded by single-column continuous breaks
    ls_col_counts = []
    for s in doc_ls.sections:
        c = s._sectPr.find(qn("w:cols"))
        val = c.get(qn("w:num")) if c is not None else "1"
        ls_col_counts.append(val or "1")
    assert "1" in ls_col_counts
    assert "2" in ls_col_counts
    assert len(ls_col_counts) >= 4  # title (1) -> body (2) -> wide diag (1) -> body (2)

    # -----------------------------------------------------------------------
    # 3. Assertions on Executive Summary (Modern Layout)
    # -----------------------------------------------------------------------
    doc_es = Document(path_es)
    # Modern layout is single-column
    for s in doc_es.sections:
        c = s._sectPr.find(qn("w:cols"))
        val = c.get(qn("w:num")) if c is not None else "1"
        assert val in (None, "1")

    # Shaded header rows in modern tables
    assert len(doc_es.tables) >= 1
    # Check that at least one table has theme.TABLE_HEADER_FILL in its header cell XML
    has_shaded_header = any(
        theme.TABLE_HEADER_FILL.lstrip("#") in tbl.rows[0].cells[0]._tc.xml
        for tbl in doc_es.tables if len(tbl.rows) > 0
    )
    assert has_shaded_header

    # Headings unnumbered in executive summary
    headings_es = [p.text for p in doc_es.paragraphs if p.style.name.startswith("Heading")]
    assert "Executive Summary" in headings_es
    assert "Strategic Recommendations" in headings_es
    assert not any(h.startswith("1 ") or h.startswith("2 ") for h in headings_es)


def test_missing_figure_spec_renders_placeholder_and_logs(tmp_path: Path, caplog):
    """Test that a missing figure_id logs a warning and renders an italic placeholder without crashing."""
    broken_res = ComposerResult(
        output_type=OutputType.LITERATURE_SURVEY,
        title="Survey Missing Figure",
        content="",
        structured=StructuredContent(
            sections=[
                DocSection(
                    heading="Architecture",
                    blocks=[
                        ContentBlock(kind="figure", figure_id="nonexistent_fig_99"),
                    ],
                ),
            ],
            figures=[],
        ),
    )
    out_file = tmp_path / "broken_fig.docx"
    with caplog.at_level(logging.WARNING):
        render_docx(broken_res, out_file)

    assert any("FigureSpec not found for figure_id: nonexistent_fig_99" in r.message for r in caplog.records)
    doc = Document(out_file)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "[Figure placeholder: nonexistent_fig_99 not found]" in text


def test_independent_table_and_figure_numbering(tmp_path: Path):
    """Verify tables and figures have separate counters across multiple blocks."""
    res = ComposerResult(
        output_type=OutputType.RESEARCH_PAPER,
        title="Numbering Verification",
        content="",
        structured=StructuredContent(
            sections=[
                DocSection(
                    heading="Data Section",
                    blocks=[
                        ContentBlock(kind="table", table_header=["Col A"], table_rows=[["Val 1"]], caption="First Table"),
                        ContentBlock(kind="figure", figure_id="fig_1", caption="First Figure"),
                        ContentBlock(kind="table", table_header=["Col B"], table_rows=[["Val 2"]], caption="Second Table"),
                        ContentBlock(kind="figure", figure_id="fig_2", caption="Second Figure"),
                    ],
                ),
            ],
            figures=[
                FigureSpec(figure_id="fig_1", kind="bar_chart", title="F1", labels=["A"], values=[1.0]),
                FigureSpec(figure_id="fig_2", kind="bar_chart", title="F2", labels=["B"], values=[2.0]),
            ],
        ),
    )
    out_file = tmp_path / "numbering.docx"
    render_docx(res, out_file)
    doc = Document(out_file)

    caption_texts = [p.text for p in doc.paragraphs if p.style.name == "Caption"]
    assert "Table 1: First Table" in caption_texts
    assert "Figure 1: First Figure" in caption_texts
    assert "Table 2: Second Table" in caption_texts
    assert "Figure 2: Second Figure" in caption_texts


def test_academic_subheading_numbering(tmp_path: Path):
    """Verify H1, H2, H3 numbering in academic mode: '1 Intro', '2.1 Subheading', etc."""
    res = ComposerResult(
        output_type=OutputType.RESEARCH_PAPER,
        title="Subheading Verification",
        content="",
        structured=StructuredContent(
            sections=[
                DocSection(heading="Introduction", blocks=[ContentBlock(kind="paragraph", text="Intro text.")]),
                DocSection(heading="## Background", blocks=[ContentBlock(kind="paragraph", text="Bg text.")]),
                DocSection(heading="### Details", blocks=[ContentBlock(kind="paragraph", text="Details text.")]),
                DocSection(heading="Methods", blocks=[ContentBlock(kind="paragraph", text="Methods text.")]),
            ],
            figures=[],
        ),
    )
    out_file = tmp_path / "subheadings.docx"
    render_docx(res, out_file)
    doc = Document(out_file)

    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert "1 Introduction" in headings
    assert "1.1 Background" in headings
    assert "1.1.1 Details" in headings
    assert "2 Methods" in headings


def test_academic_title_centered(tmp_path: Path):
    """Verify that title paragraph in academic layout is centered with zero indents."""
    res = build_research_paper_composer_result()
    out_file = tmp_path / "academic_title.docx"
    render_docx(res, out_file)
    doc = Document(out_file)

    # First paragraph is the Title
    title_p = doc.paragraphs[0]
    assert title_p.style.name == "Title"
    assert title_p.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert title_p.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert title_p.paragraph_format.first_line_indent.pt == 0
    assert title_p.paragraph_format.keep_with_next is True


def test_academic_table_cells_left_aligned(tmp_path: Path):
    """Verify that all table cell paragraphs in academic layout are left-aligned."""
    res = build_research_paper_composer_result()
    out_file = tmp_path / "academic_cells.docx"
    render_docx(res, out_file)
    doc = Document(out_file)

    assert len(doc.tables) >= 1
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    assert p.alignment == WD_ALIGN_PARAGRAPH.LEFT
                    assert p.paragraph_format.first_line_indent.pt == 0


def test_academic_caption_and_heading_keep_with_next(tmp_path: Path):
    """Verify that headings and table captions have keep_with_next set to True."""
    res = build_research_paper_composer_result()
    out_file = tmp_path / "academic_keep_with_next.docx"
    render_docx(res, out_file)
    doc = Document(out_file)

    # Check headings
    heading_paras = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert len(heading_paras) >= 3
    for hp in heading_paras:
        assert hp.paragraph_format.keep_with_next is True

    # Check table captions
    caption_paras = [p for p in doc.paragraphs if p.style.name == "Caption" and "Table" in p.text]
    assert len(caption_paras) >= 1
    for cp in caption_paras:
        assert cp.paragraph_format.keep_with_next is True