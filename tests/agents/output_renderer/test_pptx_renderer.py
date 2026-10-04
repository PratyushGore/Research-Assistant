import logging
from pathlib import Path
import tempfile

import pytest
from pptx import Presentation
from pptx.util import Inches, Pt

from backend.agents.output_renderer import theme
from backend.agents.output_renderer.pptx_renderer import _hex_to_rgb, render_pptx
from backend.schemas.schemas import (
    ComposerResult,
    FigureSpec,
    OutputType,
    SlideSpec,
    StructuredContent,
)


def sample_composer_result() -> ComposerResult:
    return ComposerResult(
        output_type=OutputType.PPT,
        title="AI Research Assistant",
        content="Presentation content.",
        sections={
            "Problem": "This is the problem statement.",
            "Literature Findings": "These are the literature findings.",
            "Own Approach/Architecture": "This is our architecture.",
            "Own Results": "These are our results.",
            "Comparison": "This is the comparison.",
            "Conclusion": "This is the conclusion.",
        },
        citations_used=["citation-paper-001"],
    )


def sample_structured_composer_result() -> ComposerResult:
    """Build a ComposerResult with hand-made SlideSpecs covering all 8 layouts."""
    fig_bar = FigureSpec(
        figure_id="fig_bar_1",
        kind="bar_chart",
        title="Publications per Year",
        labels=["2021", "2022", "2023"],
        values=[15.0, 28.0, 45.0],
        data_source="papers_per_year",
    )
    fig_diag = FigureSpec(
        figure_id="fig_diag_1",
        kind="diagram",
        title="Pipeline Architecture",
        nodes=["Search", "Ingest", "Vector", "Summarize", "Verify", "Bid-Price Module", "Compose"],
        edges=[
            ("Search", "Ingest"),
            ("Ingest", "Vector"),
            ("Vector", "Summarize"),
            ("Summarize", "Verify"),
            ("Verify", "Bid-Price Module"),
            ("Bid-Price Module", "Compose"),
            ("Bid-Price Module", "Ingest"),
        ],
    )

    slides = [
        # 1. Title layout
        SlideSpec(
            layout="title",
            title="Multi-Agent AI Research System",
            bullets=["An Empirical Study on Grounded Literature Synthesis"],
            notes="Introduce study objectives and multi-agent approach.",
        ),
        # 2. Agenda layout
        SlideSpec(
            layout="agenda",
            title="Presentation Agenda",
            bullets=[
                "Motivation & Research Problem",
                "System Architecture & Pipeline",
                "Empirical Findings & Benchmarks",
                "Comparative Model Evaluation",
                "Limitations & Future Work",
            ],
            notes="Give a high-level roadmap of the talk.",
        ),
        # 3. Section divider layout
        SlideSpec(
            layout="section_divider",
            title="Section 1: Architecture & Design",
            bullets=["Detailed breakdown of agent interactions"],
            notes="Transition from problem context to system architecture.",
        ),
        # 4. Bullets layout (5 bullets)
        SlideSpec(
            layout="bullets",
            title="Key Empirical Findings",
            bullets=[
                "Finding 1: Zero hallucinated citations across evaluated benchmarks.",
                "Finding 2: 35% reduction in end-to-end processing latency.",
                "Finding 3: High precision claim extraction from complex PDF papers.",
                "Finding 4: Robust cross-paper contradiction detection.",
                "Finding 5: Fully grounded verification pipeline ensures trustworthiness.",
            ],
            notes="Emphasize zero-hallucination and latency numbers.",
        ),
        # 5. Table layout
        SlideSpec(
            layout="table",
            title="Benchmark Comparison",
            table_header=["Method", "Accuracy (%)", "Latency (s)", "Memory (MB)"],
            table_rows=[
                ["Baseline RAG", "74.5", "12.4", "1024"],
                ["Ours (v1)", "84.2", "8.1", "820"],
                ["Ours (v2)", "91.8", "4.3", "650"],
            ],
            notes="Point out 17.3% accuracy gain and 2.8x speedup.",
        ),
        # 6. Chart layout
        SlideSpec(
            layout="chart",
            title="Research Growth Over Time",
            figure_id="fig_bar_1",
            notes="Highlight the accelerating adoption rate in recent years.",
        ),
        # 7. Diagram layout
        SlideSpec(
            layout="diagram",
            title="Agent Pipeline Workflow",
            figure_id="fig_diag_1",
            notes="Explain the sequential handoffs between specialized agents.",
        ),
        # 8. Closing layout
        SlideSpec(
            layout="closing",
            title="Thank You & Discussion",
            bullets=[
                "Q&A Session",
                "Contact: research@example.com",
                "Repository: github.com/example/research-assistant",
            ],
            notes="Open the floor to audience questions.",
        ),
    ]

    structured = StructuredContent(
        slides=slides,
        figures=[fig_bar, fig_diag],
    )

    return ComposerResult(
        output_type=OutputType.PPT,
        title="Multi-Agent AI Research System",
        content="Overview content.",
        structured=structured,
    )


# ---------------------------------------------------------------------------
# Existing Fallback Tests (Preserved)
# ---------------------------------------------------------------------------

def test_render_pptx_creates_file(tmp_path: Path):
    output_path = tmp_path / "research_presentation.pptx"

    result = render_pptx(
        sample_composer_result(),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.is_file()


def test_render_pptx_contains_title_and_sections(tmp_path: Path):
    output_path = tmp_path / "research_presentation.pptx"

    render_pptx(
        sample_composer_result(),
        output_path,
    )

    presentation = Presentation(str(output_path))

    text = "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )

    assert "AI Research Assistant" in text
    assert "Problem" in text
    assert "This is the problem statement." in text
    assert "Literature Findings" in text
    assert "Own Approach/Architecture" in text
    assert "Own Results" in text
    assert "Comparison" in text
    assert "Conclusion" in text


def test_render_pptx_creates_parent_directory(tmp_path: Path):
    output_path = (
        tmp_path
        / "generated"
        / "nested"
        / "presentation.pptx"
    )

    render_pptx(
        sample_composer_result(),
        output_path,
    )

    assert output_path.exists()


def test_render_pptx_preserves_section_order(tmp_path: Path):
    output_path = tmp_path / "ordered.pptx"

    render_pptx(
        sample_composer_result(),
        output_path,
    )

    presentation = Presentation(str(output_path))

    slide_titles = [
        slide.shapes.title.text
        for slide in presentation.slides
        if slide.shapes.title is not None
    ]

    assert slide_titles[0] == "AI Research Assistant"
    assert slide_titles.index("Problem") < slide_titles.index(
        "Literature Findings"
    )
    assert slide_titles.index("Literature Findings") < slide_titles.index(
        "Own Approach/Architecture"
    )
    assert slide_titles.index("Own Approach/Architecture") < slide_titles.index(
        "Own Results"
    )
    assert slide_titles.index("Own Results") < slide_titles.index(
        "Comparison"
    )
    assert slide_titles.index("Comparison") < slide_titles.index(
        "Conclusion"
    )


def test_render_pptx_rejects_non_pptx_path(tmp_path: Path):
    output_path = tmp_path / "presentation.pdf"

    try:
        render_pptx(
            sample_composer_result(),
            output_path,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Output path must have a .pptx extension" in str(exc)


# ---------------------------------------------------------------------------
# Structured Presentation Tests (Task C)
# ---------------------------------------------------------------------------

def test_render_pptx_fallback_cleans_hardcoded_subtitle(tmp_path: Path):
    """Fallback path must not include the old hardcoded subtitle."""
    output_path = tmp_path / "fallback.pptx"
    render_pptx(sample_composer_result(), output_path)

    prs = Presentation(str(output_path))
    title_slide = prs.slides[0]
    if len(title_slide.placeholders) > 1:
        subtitle_text = title_slide.placeholders[1].text
        assert "Multi-Agent AI Research & Publication Assistant" not in subtitle_text
        assert subtitle_text == ""


def test_render_pptx_structured_all_layouts(tmp_path: Path):
    """
    Test 16:9 structured deck covering all 8 layouts:
    - 8 slides
    - 16:9 widescreen dimensions
    - Native table and native chart exist
    - Speaker notes populated
    - 5-bullet slide fits within slide height bounds
    - Also writes one sample file to temp dir for manual review.
    """
    output_path = tmp_path / "structured_deck.pptx"
    cr = sample_structured_composer_result()

    result = render_pptx(cr, output_path)
    assert result == output_path
    assert output_path.exists()

    # Write a copy to the system temp directory for manual inspection
    sample_dir = Path(tempfile.gettempdir())
    sample_file = sample_dir / "sample_research_presentation.pptx"
    sample_file.write_bytes(output_path.read_bytes())
    print(f"\n[SAMPLE PPTX FILE] Created at: {sample_file.resolve()}")

    # Reopen and assert structure
    prs = Presentation(str(output_path))

    # 1. Slide count
    assert len(prs.slides) == 8

    # 2. 16:9 dimensions (13.333 x 7.5 inches)
    assert prs.slide_width.inches == pytest.approx(13.333, abs=0.01)
    assert prs.slide_height.inches == pytest.approx(7.5, abs=0.01)

    # 3. Native table on slide index 4 (5th slide)
    table_slide = prs.slides[4]
    table_shapes = [s for s in table_slide.shapes if s.has_table]
    assert len(table_shapes) == 1, "Expected native table shape on table slide"
    tbl = table_shapes[0].table
    assert len(tbl.rows) == 4  # 1 header + 3 rows
    assert len(tbl.columns) == 4
    assert tbl.cell(0, 0).text == "Method"
    assert tbl.cell(1, 0).text == "Baseline RAG"
    assert tbl.cell(3, 1).text == "91.8"

    # 4. Native chart on slide index 5 (6th slide)
    chart_slide = prs.slides[5]
    chart_shapes = [s for s in chart_slide.shapes if s.has_chart]
    assert len(chart_shapes) == 1, "Expected native chart shape on chart slide"
    chart = chart_shapes[0].chart
    assert len(chart.series) >= 1
    assert chart.series[0].name == "Publications per Year"

    # 5. Diagram slide has editable shapes (rounded rectangles and arrows)
    diag_slide = prs.slides[6]
    text_in_shapes = [s.text for s in diag_slide.shapes if hasattr(s, "text") and s.text]
    for expected_node in ["Search", "Ingest", "Vector", "Summarize", "Verify", "Bid-Price Module", "Compose"]:
        assert any(expected_node in t for t in text_in_shapes), f"Missing node {expected_node}"

    # 6. Speaker notes present across slides
    assert "Introduce study objectives" in prs.slides[0].notes_slide.notes_text_frame.text
    assert "Give a high-level roadmap" in prs.slides[1].notes_slide.notes_text_frame.text
    assert "Transition from problem context" in prs.slides[2].notes_slide.notes_text_frame.text
    assert "Emphasize zero-hallucination" in prs.slides[3].notes_slide.notes_text_frame.text
    assert "Point out 17.3% accuracy gain" in prs.slides[4].notes_slide.notes_text_frame.text
    assert "Highlight the accelerating adoption" in prs.slides[5].notes_slide.notes_text_frame.text
    assert "Explain the sequential handoffs" in prs.slides[6].notes_slide.notes_text_frame.text
    assert "Open the floor" in prs.slides[7].notes_slide.notes_text_frame.text

    # 7. 5-bullet slide (slide index 3): no text frame overflowing rough height estimate
    bullet_slide = prs.slides[3]
    bullet_boxes = [
        s for s in bullet_slide.shapes
        if s.has_text_frame and len(s.text_frame.paragraphs) == 5
    ]
    assert len(bullet_boxes) == 1, "Expected 5-bullet text box on bullets slide"
    box = bullet_boxes[0]

    # Bounding box must be contained within slide boundaries (top + height <= 7.0 inches)
    top_in = box.top.inches
    height_in = box.height.inches
    assert top_in + height_in <= 7.0, f"Box overflows: top {top_in} + height {height_in} > 7.0"

    # Verify font size was auto-sized appropriately
    p0 = box.text_frame.paragraphs[0]
    assert p0.font.size is not None
    assert p0.font.size <= Pt(18), "Font size should not exceed 18pt for 5 bullets"

    # Rough height estimate for 5 lines of text: 5 * (15pt * 1.2 + 12pt space) ≈ 150pt ≈ 2.1 in < 4.6 in
    estimated_text_height_in = (5 * (p0.font.size.pt * 1.25 + 12.0)) / 72.0
    assert estimated_text_height_in < 4.0, "Estimated text height exceeds available space"

    # 8. Slide numbers in footers on non-title slides (slides 1 to 6)
    for idx in range(1, 7):
        slide = prs.slides[idx]
        has_slide_number = any(
            s.has_text_frame and str(idx + 1) in s.text_frame.text
            for s in slide.shapes
        )
        assert has_slide_number, f"Slide {idx + 1} missing footer slide number"


def test_render_pptx_missing_figure_warning(tmp_path: Path, caplog):
    """When a figure_id is not found, log a warning and render a placeholder."""
    output_path = tmp_path / "missing_fig.pptx"
    slides = [
        SlideSpec(
            layout="chart",
            title="Missing Chart",
            figure_id="non_existent_chart_id",
        ),
        SlideSpec(
            layout="diagram",
            title="Missing Diagram",
            figure_id="non_existent_diag_id",
        ),
    ]
    cr = ComposerResult(
        output_type=OutputType.PPT,
        title="Test Missing Figures",
        content="Overview",
        structured=StructuredContent(slides=slides, figures=[]),
    )

    with caplog.at_level(logging.WARNING):
        render_pptx(cr, output_path)

    # Verify warning was logged
    warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("non_existent_chart_id" in w for w in warnings)
    assert any("non_existent_diag_id" in w for w in warnings)

    # Verify placeholder is present on both slides
    prs = Presentation(str(output_path))
    slide0_text = "\n".join(s.text for s in prs.slides[0].shapes if hasattr(s, "text"))
    slide1_text = "\n".join(s.text for s in prs.slides[1].shapes if hasattr(s, "text"))

    assert "[Figure Missing: non_existent_chart_id]" in slide0_text
    assert "[Figure Missing: non_existent_diag_id]" in slide1_text


# ---------------------------------------------------------------------------
# Layout, Legibility, and Geometry Validation Tests (Task F)
# ---------------------------------------------------------------------------

def _bbox_intersects(
    b1: tuple[float, float, float, float],
    b2: tuple[float, float, float, float],
    eps: float = 1e-4,
) -> bool:
    """
    Check if two 2D axis-aligned bounding boxes intersect.
    Bounding box format: (left, top, right, bottom)
    """
    l1, t1, r1, bot1 = b1
    l2, t2, r2, bot2 = b2
    return not (r1 <= l2 + eps or l1 >= r2 - eps or bot1 <= t2 + eps or t1 >= bot2 - eps)


def test_layout_minimum_font_sizes(tmp_path: Path):
    """
    Assert that body text across all layouts meets minimum font size >= 16pt
    (and >= 11pt on tables).
    """
    output_path = tmp_path / "min_font_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    # Slide 0: Title layout -> subtitle paragraph >= 16pt
    slide0_tf = prs.slides[0].shapes[1].text_frame
    assert len(slide0_tf.paragraphs) >= 2
    assert slide0_tf.paragraphs[1].font.size >= Pt(16)

    # Slide 1: Agenda layout -> all items >= 16pt
    agenda_box = [s for s in prs.slides[1].shapes if s.has_text_frame and len(s.text_frame.paragraphs) >= 4][0]
    for p in agenda_box.text_frame.paragraphs:
        assert p.font.size >= Pt(16)

    # Slide 2: Section divider layout -> subtitle >= 16pt
    slide2_tf = prs.slides[2].shapes[1].text_frame
    assert len(slide2_tf.paragraphs) >= 2
    assert slide2_tf.paragraphs[1].font.size >= Pt(16)

    # Slide 3: Bullets layout -> all bullets >= 16pt
    bullet_box = [s for s in prs.slides[3].shapes if s.has_text_frame and len(s.text_frame.paragraphs) >= 5][0]
    for p in bullet_box.text_frame.paragraphs:
        assert p.font.size >= Pt(16)

    # Slide 4: Table layout -> header >= 14pt (16pt), data cells >= 11pt (14pt)
    tbl = [s for s in prs.slides[4].shapes if s.has_table][0].table
    for c_idx in range(len(tbl.columns)):
        header_p = tbl.cell(0, c_idx).text_frame.paragraphs[0]
        assert header_p.font.size >= Pt(14)
    for r_idx in range(1, len(tbl.rows)):
        for c_idx in range(len(tbl.columns)):
            data_p = tbl.cell(r_idx, c_idx).text_frame.paragraphs[0]
            assert data_p.font.size >= Pt(11)

    # Slide 6: Diagram layout -> all node labels >= 14pt (set to 16pt)
    diag_nodes = ["Search", "Ingest", "Vector", "Summarize", "Verify", "Bid-Price Module", "Compose"]
    for s in prs.slides[6].shapes:
        if hasattr(s, "text") and s.text in diag_nodes:
            for p in s.text_frame.paragraphs:
                assert p.font.size >= Pt(14)

    # Slide 7: Closing layout -> subtitle paragraphs >= 16pt
    closing_tf = prs.slides[7].shapes[1].text_frame
    for p in closing_tf.paragraphs[1:]:
        assert p.font.size >= Pt(16)


def test_all_shapes_within_slide_bounds(tmp_path: Path):
    """Assert that no shape extends beyond the 16:9 slide boundaries on any slide."""
    output_path = tmp_path / "bounds_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    slide_w = prs.slide_width.inches
    slide_h = prs.slide_height.inches
    eps = 0.01  # tolerance for floating point coordinates

    for s_idx, slide in enumerate(prs.slides):
        for shape_idx, shape in enumerate(slide.shapes):
            l = shape.left.inches
            t = shape.top.inches
            r = l + shape.width.inches
            b = t + shape.height.inches
            assert l >= -eps, f"Slide {s_idx+1} shape {shape_idx} left {l} < 0"
            assert t >= -eps, f"Slide {s_idx+1} shape {shape_idx} top {t} < 0"
            assert r <= slide_w + eps, f"Slide {s_idx+1} shape {shape_idx} right {r} > {slide_w}"
            assert b <= slide_h + eps, f"Slide {s_idx+1} shape {shape_idx} bottom {b} > {slide_h}"


def test_diagram_connector_geometry_no_node_intersections(tmp_path: Path):
    """
    Assert that on the diagram slide, no connector's bounding box intersects
    with any node's bounding box.
    """
    output_path = tmp_path / "geometry_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    diag_slide = prs.slides[6]
    diag_nodes = ["Search", "Ingest", "Vector", "Summarize", "Verify", "Bid-Price Module", "Compose"]

    node_shapes = [s for s in diag_slide.shapes if hasattr(s, "text") and s.text in diag_nodes]
    connector_shapes = [s for s in diag_slide.shapes if hasattr(s, "begin_x")]

    assert len(node_shapes) == 7
    assert len(connector_shapes) >= 6

    for ci, conn in enumerate(connector_shapes):
        c_box = (
            conn.left.inches,
            conn.top.inches,
            conn.left.inches + conn.width.inches,
            conn.top.inches + conn.height.inches,
        )
        for ni, node in enumerate(node_shapes):
            n_box = (
                node.left.inches,
                node.top.inches,
                node.left.inches + node.width.inches,
                node.top.inches + node.height.inches,
            )
            assert not _bbox_intersects(c_box, n_box), (
                f"Connector {ci} ({c_box}) intersects node '{node.text}' ({n_box})"
            )


def test_diagram_node_text_color_contrast(tmp_path: Path):
    """
    Assert that every diagram node label has explicit text color differing from
    its fill color (high contrast), on both paragraph and all runs.
    """
    output_path = tmp_path / "contrast_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    diag_slide = prs.slides[6]
    diag_nodes = ["Search", "Ingest", "Vector", "Summarize", "Verify", "Bid-Price Module", "Compose"]

    found_nodes = 0
    for shape in diag_slide.shapes:
        if hasattr(shape, "text") and shape.text in diag_nodes:
            found_nodes += 1
            fill_rgb = shape.fill.fore_color.rgb
            assert fill_rgb is not None, f"Node '{shape.text}' has no fill color"
            for p in shape.text_frame.paragraphs:
                assert p.font.color.rgb is not None
                assert p.font.color.rgb != fill_rgb, f"Paragraph text color matches fill in '{shape.text}'"
                for r in p.runs:
                    assert r.font.color.rgb is not None
                    assert r.font.color.rgb != fill_rgb, f"Run text color matches fill in '{shape.text}'"

    assert found_nodes == 7


def test_chart_integer_value_axis_and_data_labels(tmp_path: Path):
    """
    Assert that when chart values are whole numbers, the value axis major_unit == 1,
    the number format is '0', and data labels are enabled.
    """
    output_path = tmp_path / "chart_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    chart_slide = prs.slides[5]
    chart = [s for s in chart_slide.shapes if s.has_chart][0].chart

    val_axis = chart.value_axis
    assert val_axis.major_unit == 1
    assert val_axis.tick_labels.number_format == "0"
    assert val_axis.tick_labels.font.size >= Pt(12)
    assert chart.category_axis.tick_labels.font.size >= Pt(12)

    assert chart.plots[0].has_data_labels is True
    assert chart.plots[0].data_labels.font.size >= Pt(12)
    assert chart.has_legend is False
    assert chart.has_title is False


def test_dense_table_font_stepping(tmp_path: Path):
    """
    Assert that dense tables step down font size (down to minimum 11pt)
    and do not overflow the slide boundaries.
    """
    output_path = tmp_path / "dense_table.pptx"
    dense_rows = [
        [f"Metric {i}", f"Long descriptive value result that wraps across lines {i}", str(100 + i * 5)]
        for i in range(12)
    ]
    slide = SlideSpec(
        layout="table",
        title="Dense Experimental Benchmark Results Across Models",
        table_header=["Metric Name", "Detailed Observations & Methodology", "Score"],
        table_rows=dense_rows,
    )
    cr = ComposerResult(
        output_type=OutputType.PPT,
        title="Dense Table Presentation",
        content="Overview",
        structured=StructuredContent(slides=[slide], figures=[]),
    )
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    tbl_slide = prs.slides[0]
    tbl_shape = [s for s in tbl_slide.shapes if s.has_table][0]
    tbl = tbl_shape.table

    # Assert shape is within slide
    assert tbl_shape.top.inches >= 0
    assert (tbl_shape.top.inches + tbl_shape.height.inches) <= 7.5

    # Check stepped down font size
    body_p = tbl.cell(1, 0).text_frame.paragraphs[0]
    assert body_p.font.size >= Pt(11)
    assert body_p.font.size <= Pt(13)


def test_short_bullets_and_agenda_large_typography(tmp_path: Path):
    """
    Assert that short bullets and agenda items use 22-24pt font,
    agenda items are numbered, and visual accent bars are added.
    """
    output_path = tmp_path / "typography_deck.pptx"
    slides = [
        SlideSpec(
            layout="agenda",
            title="Strategic Road-map",
            bullets=["Core Discovery", "Methodology", "Evaluation"],
        ),
        SlideSpec(
            layout="bullets",
            title="Key Takeaways",
            bullets=["Short point A", "Short point B", "Short point C"],
        ),
    ]
    cr = ComposerResult(
        output_type=OutputType.PPT,
        title="Typography Presentation",
        content="Overview",
        structured=StructuredContent(slides=slides, figures=[]),
    )
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    # Agenda slide
    agenda_slide = prs.slides[0]
    agenda_box = [s for s in agenda_slide.shapes if s.has_text_frame and len(s.text_frame.paragraphs) == 3][0]
    for p in agenda_box.text_frame.paragraphs:
        assert p.font.size >= Pt(22)
        # Should be numbered
        assert p.text[0].isdigit()

    # Bullets slide
    bullet_slide = prs.slides[1]
    bullet_box = [s for s in bullet_slide.shapes if s.has_text_frame and len(s.text_frame.paragraphs) == 3][0]
    for p in bullet_box.text_frame.paragraphs:
        assert p.font.size >= Pt(22)

    # Check left accent bar on both slides
    for sl in [agenda_slide, bullet_slide]:
        has_accent_bar = any(
            s.width.inches <= 0.1 and s.height.inches >= 2.0
            for s in sl.shapes
        )
        assert has_accent_bar, "Expected left accent bar shape on slide"


def test_footer_slide_numbers_typography(tmp_path: Path):
    """Assert footer slide numbers are in 12pt with MUTED color."""
    output_path = tmp_path / "footer_deck.pptx"
    cr = sample_structured_composer_result()
    render_pptx(cr, output_path)
    prs = Presentation(str(output_path))

    for idx in range(1, 7):
        slide = prs.slides[idx]
        footer_boxes = [
            s for s in slide.shapes
            if s.has_text_frame and s.text_frame.text.strip() == str(idx + 1)
        ]
        assert len(footer_boxes) == 1
        fp = footer_boxes[0].text_frame.paragraphs[0]
        assert fp.font.size == Pt(12)
        assert fp.font.color.rgb == _hex_to_rgb(theme.MUTED)