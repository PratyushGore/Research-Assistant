from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Emu, Inches, Pt

from backend.agents.output_renderer import theme
from backend.schemas.schemas import ComposerResult, FigureSpec, SlideSpec

logger = logging.getLogger("research_assistant.output_renderer.pptx")


def _hex_to_rgb(hex_str: str) -> RGBColor:
    """Convert a 6-hex-digit color string (e.g. '#1E3A8A') to RGBColor."""
    clean = hex_str.lstrip("#")
    return RGBColor(int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _get_blank_layout(prs: Presentation) -> Any:
    """Find a blank slide layout (0 placeholders) or fall back to layout 6."""
    for layout in prs.slide_layouts:
        if len(layout.placeholders) == 0:
            return layout
    if len(prs.slide_layouts) > 6:
        return prs.slide_layouts[6]
    return prs.slide_layouts[-1]


def _calculate_bullet_typography(
    bullets: list[str],
    is_agenda: bool = False,
) -> tuple[float, float]:
    """
    Compute (font_size_pt, space_after_pt) so bullets and agenda items fill the slide
    without overflowing.
    Uses 22-24pt for up to 4 short bullets, stepping down to a minimum of 16pt only
    when needed, with generous paragraph spacing.
    """
    if not bullets:
        return 24.0, 24.0

    num_bullets = len(bullets)
    total_chars = sum(len(b) for b in bullets)
    max_bullet_chars = max(len(b) for b in bullets)

    # Estimate wrapped lines (~70 chars per line with margins and accent bar)
    estimated_lines = sum(max(1, (len(b) + 69) // 70) for b in bullets)

    # Calculate starting point:
    if num_bullets <= 3 and total_chars <= 180 and max_bullet_chars <= 80:
        font_size = 24.0
        space_after = 24.0
    elif num_bullets <= 4 and total_chars <= 320 and max_bullet_chars <= 120:
        font_size = 22.0
        space_after = 20.0
    elif num_bullets <= 5 and total_chars <= 450:
        font_size = 18.0
        space_after = 16.0
    elif num_bullets <= 6 and total_chars <= 600:
        font_size = 17.0
        space_after = 14.0
    else:
        font_size = 16.0
        space_after = 12.0

    # Available vertical height in points: (6.6" - 1.8") * 72 = 345.6 pt
    available_pt = 345.0
    estimated_height_pt = (estimated_lines * font_size * 1.3) + ((num_bullets - 1) * space_after)

    if estimated_height_pt > available_pt:
        # Step down spacing first
        excess = estimated_height_pt - available_pt
        space_reduction = excess / max(1, num_bullets - 1)
        space_after = max(6.0, space_after - space_reduction)
        estimated_height_pt = (estimated_lines * font_size * 1.3) + ((num_bullets - 1) * space_after)

    if estimated_height_pt > available_pt and font_size > 16.0:
        font_size = 16.0
        space_after = max(6.0, (available_pt - (estimated_lines * 16.0 * 1.3)) / max(1, num_bullets - 1))
        space_after = min(14.0, max(4.0, space_after))

    # Guardrail check: never shrink below 16.0 pt
    font_size = max(16.0, font_size)

    return font_size, space_after


def _add_slide_title(slide: Any, title_text: str) -> None:
    """Render a consistent top title bar for content slides."""
    tb = slide.shapes.add_textbox(
        Inches(0.8), Inches(0.6), Inches(11.733), Inches(0.8)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title_text
    p.font.name = theme.FONT_PPT
    p.font.size = Pt(theme.FONT_SIZE_TITLE)
    p.font.bold = True
    p.font.color.rgb = _hex_to_rgb(theme.PRIMARY)

    # Subtle accent rule under the title bar
    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.8), Inches(1.45), Inches(11.733), Inches(0.02)
    )
    rule.fill.solid()
    rule.fill.fore_color.rgb = _hex_to_rgb(theme.ACCENT)
    rule.line.fill.background()


def _add_missing_figure_placeholder(slide: Any, figure_id: Optional[str]) -> None:
    """Render a visible missing-figure placeholder text box."""
    tb = slide.shapes.add_textbox(
        Inches(2.0), Inches(2.8), Inches(9.333), Inches(1.8)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"[Figure Missing: {figure_id or 'No ID provided'}]"
    p.font.name = theme.FONT_PPT
    p.font.size = Pt(theme.FONT_SIZE_H1)
    p.font.color.rgb = _hex_to_rgb(theme.MUTED)
    p.alignment = PP_ALIGN.CENTER


def _render_title_or_closing(
    slide: Any,
    slide_spec: SlideSpec,
    is_closing: bool = False,
) -> None:
    """Render full-bleed primary background title/closing slide."""
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        0, 0,
        Inches(theme.SLIDE_WIDTH_INCHES),
        Inches(theme.SLIDE_HEIGHT_INCHES),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hex_to_rgb(theme.PRIMARY)
    bg.line.fill.background()

    if is_closing:
        # Closing slide: large title, up to 3 short lines of subtitle text centered
        tb = slide.shapes.add_textbox(
            Inches(1.0), Inches(1.95), Inches(11.333), Inches(3.6)
        )
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE

        p = tf.paragraphs[0]
        p.text = slide_spec.title
        p.font.name = theme.FONT_PPT
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = _hex_to_rgb(theme.BACKGROUND)
        p.alignment = PP_ALIGN.CENTER

        subtitle_lines = slide_spec.bullets[:3] if slide_spec.bullets else []
        for line_text in subtitle_lines:
            sub_p = tf.add_paragraph()
            sub_p.text = line_text
            sub_p.font.name = theme.FONT_PPT
            sub_p.font.size = Pt(18)
            sub_p.font.color.rgb = _hex_to_rgb(theme.TABLE_HEADER_FILL)
            sub_p.alignment = PP_ALIGN.CENTER
            sub_p.space_before = Pt(theme.SPACING_MD)
    else:
        tb = slide.shapes.add_textbox(
            Inches(1.0), Inches(2.2), Inches(11.333), Inches(2.8)
        )
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE

        p = tf.paragraphs[0]
        p.text = slide_spec.title
        p.font.name = theme.FONT_PPT
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = _hex_to_rgb(theme.BACKGROUND)

        # Subtitle from SlideSpec (use bullets[0] if present)
        if slide_spec.bullets:
            sub_p = tf.add_paragraph()
            sub_p.text = slide_spec.bullets[0]
            sub_p.font.name = theme.FONT_PPT
            sub_p.font.size = Pt(theme.FONT_SIZE_H1)
            sub_p.font.color.rgb = _hex_to_rgb(theme.TABLE_HEADER_FILL)
            sub_p.space_before = Pt(theme.SPACING_MD)


def _render_section_divider(slide: Any, slide_spec: SlideSpec) -> None:
    """Render accent-colored slide with large title."""
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        0, 0,
        Inches(theme.SLIDE_WIDTH_INCHES),
        Inches(theme.SLIDE_HEIGHT_INCHES),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hex_to_rgb(theme.ACCENT)
    bg.line.fill.background()

    tb = slide.shapes.add_textbox(
        Inches(1.0), Inches(2.3), Inches(11.333), Inches(2.6)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE

    p = tf.paragraphs[0]
    p.text = slide_spec.title
    p.font.name = theme.FONT_PPT
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = _hex_to_rgb(theme.BACKGROUND)

    if slide_spec.bullets:
        sub_p = tf.add_paragraph()
        sub_p.text = slide_spec.bullets[0]
        sub_p.font.name = theme.FONT_PPT
        sub_p.font.size = Pt(theme.FONT_SIZE_H1)
        sub_p.font.color.rgb = _hex_to_rgb(theme.TABLE_HEADER_FILL)
        sub_p.space_before = Pt(theme.SPACING_MD)


def _render_bullets(
    slide: Any,
    slide_spec: SlideSpec,
    is_agenda: bool = False,
) -> None:
    """Render agenda or bullets slide with generous typography and balanced vertical placement."""
    _add_slide_title(slide, slide_spec.title)

    bullets = slide_spec.bullets or []
    if not bullets:
        return

    font_size, space_after = _calculate_bullet_typography(bullets, is_agenda=is_agenda)

    num_bullets = len(bullets)
    estimated_lines = sum(max(1, (len(b) + 69) // 70) for b in bullets)
    estimated_height_pt = (estimated_lines * font_size * 1.3) + ((num_bullets - 1) * space_after)
    estimated_height_in = estimated_height_pt / 72.0

    # Content area vertically between 1.8" and 6.6" (available height = 4.8")
    available_h_in = 4.8
    if estimated_height_in > available_h_in:
        logger.warning(
            "Slide '%s' text content exceeds vertical content area at minimum font size (%.1f pt > %.1f pt)",
            slide_spec.title,
            estimated_height_pt,
            available_h_in * 72.0,
        )

    # Position text block nicely balanced in the content area
    box_height_in = min(available_h_in, max(2.5, estimated_height_in + 0.4))
    if estimated_height_in < 4.0:
        box_top_in = 1.8 + (available_h_in - box_height_in) / 2.0
        box_top_in = max(1.8, min(box_top_in, 2.5))
    else:
        box_top_in = 1.8

    # Add left accent bar for visual structure
    accent_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(1.0),
        Inches(box_top_in),
        Inches(0.04),
        Inches(box_height_in),
    )
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = _hex_to_rgb(theme.ACCENT)
    accent_bar.line.fill.background()

    # Add main text box
    box = slide.shapes.add_textbox(
        Inches(1.2),
        Inches(box_top_in),
        Inches(10.8),
        Inches(box_height_in),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE

    for i, bullet_text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        clean = bullet_text.strip()
        if is_agenda:
            # Numbered items for agenda
            if not (clean and clean[0].isdigit() and ("." in clean[:4] or " " in clean[:4])):
                display_text = f"{i + 1:02d}.  {clean}"
            else:
                display_text = clean
        else:
            display_text = clean

        p.text = display_text
        p.font.name = theme.FONT_PPT
        p.font.size = Pt(font_size)
        p.font.color.rgb = _hex_to_rgb(theme.TEXT)
        p.level = 0
        p.space_after = Pt(space_after)
        p.line_spacing = 1.2

        for run in p.runs:
            run.font.name = theme.FONT_PPT
            run.font.size = Pt(font_size)
            run.font.color.rgb = _hex_to_rgb(theme.TEXT)


def _render_table(slide: Any, slide_spec: SlideSpec) -> None:
    """Render styled native PPTX table filling the content area with proportional columns and wrapping."""
    _add_slide_title(slide, slide_spec.title)

    has_header = bool(slide_spec.table_header)
    rows_data = slide_spec.table_rows or []
    total_rows = (1 if has_header else 0) + len(rows_data)

    if total_rows == 0:
        _add_missing_figure_placeholder(slide, "Empty table")
        return

    num_cols = len(slide_spec.table_header) if has_header else (len(rows_data[0]) if rows_data else 1)
    num_cols = max(num_cols, 1)

    # Calculate column proportions based on max character length per column
    col_weights: list[float] = []
    for c_idx in range(num_cols):
        h_len = len(str(slide_spec.table_header[c_idx])) if (has_header and c_idx < len(slide_spec.table_header)) else 0
        r_lens = [len(str(r[c_idx])) for r in rows_data if c_idx < len(r)]
        max_col_len = max([h_len] + r_lens + [4])
        col_weights.append(max(float(max_col_len), 3.0))

    total_weight = sum(col_weights)
    table_width = Inches(11.333)
    table_left = Inches(1.0)
    avail_height = Inches(4.8)

    # Size row heights to fill the content area, capping tall rows
    target_row_height = avail_height / total_rows
    max_row_height = Inches(0.85)
    min_row_height = Inches(0.35)
    row_height = max(min_row_height, min(target_row_height, max_row_height))
    table_height = min(avail_height, row_height * total_rows)

    # Vertically center the table in the content area (1.8" to 6.6")
    table_top = Inches(1.8) + (avail_height - table_height) / 2.0

    # Step font down if dense, but minimum 11pt
    max_cell_chars = max(
        [len(str(h)) for h in (slide_spec.table_header or [])]
        + [len(str(c)) for r in rows_data for c in r]
        + [0]
    )

    if total_rows > 10 or max_cell_chars > 80:
        header_font_size = 13.0
        body_font_size = theme.TABLE_BODY_MIN_FONT_SIZE
    elif total_rows > 7 or max_cell_chars > 50:
        header_font_size = 14.0
        body_font_size = 12.0
    elif total_rows > 5 or max_cell_chars > 30:
        header_font_size = 15.0
        body_font_size = 13.0
    else:
        header_font_size = theme.TABLE_HEADER_FONT_SIZE
        body_font_size = theme.TABLE_BODY_FONT_SIZE

    # Check for overflow
    estimated_table_pt = total_rows * (body_font_size * 1.4 + 14.0)
    if estimated_table_pt > avail_height.pt:
        logger.warning(
            "Slide '%s' table content is dense and may be tight in content area (estimated %.1f pt > %.1f pt)",
            slide_spec.title,
            estimated_table_pt,
            avail_height.pt,
        )

    tbl_shape = slide.shapes.add_table(
        total_rows,
        num_cols,
        Emu(int(table_left)),
        Emu(int(table_top)),
        Emu(int(table_width)),
        Emu(int(table_height)),
    )
    table = tbl_shape.table

    # Set column widths proportionally
    min_col_w = Inches(1.0)
    for c_idx, weight in enumerate(col_weights):
        col_w = max(min_col_w, table_width * (weight / total_weight))
        table.columns[c_idx].width = Emu(int(col_w))

    # Set row heights
    for r_idx in range(total_rows):
        table.rows[r_idx].height = Emu(int(row_height))

    cur_row = 0
    if has_header:
        for c_idx in range(num_cols):
            cell = table.cell(0, c_idx)
            cell.text = str(slide_spec.table_header[c_idx]) if c_idx < len(slide_spec.table_header) else ""
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.12)
            cell.margin_right = Inches(0.12)
            cell.margin_top = Inches(0.06)
            cell.margin_bottom = Inches(0.06)
            cell.text_frame.word_wrap = True
            cell.fill.solid()
            cell.fill.fore_color.rgb = _hex_to_rgb(theme.TABLE_HEADER_FILL)
            for p in cell.text_frame.paragraphs:
                p.font.name = theme.FONT_PPT
                p.font.size = Pt(header_font_size)
                p.font.bold = True
                p.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
                for r in p.runs:
                    r.font.name = theme.FONT_PPT
                    r.font.size = Pt(header_font_size)
                    r.font.bold = True
                    r.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
        cur_row = 1

    for r_idx, r_data in enumerate(rows_data):
        fill_hex = theme.TABLE_STRIPE_FILL if r_idx % 2 == 1 else theme.BACKGROUND
        for c_idx in range(num_cols):
            cell = table.cell(cur_row + r_idx, c_idx)
            cell.text = str(r_data[c_idx]) if c_idx < len(r_data) else ""
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.12)
            cell.margin_right = Inches(0.12)
            cell.margin_top = Inches(0.06)
            cell.margin_bottom = Inches(0.06)
            cell.text_frame.word_wrap = True
            cell.fill.solid()
            cell.fill.fore_color.rgb = _hex_to_rgb(fill_hex)
            for p in cell.text_frame.paragraphs:
                p.font.name = theme.FONT_PPT
                p.font.size = Pt(body_font_size)
                p.font.bold = False
                p.font.color.rgb = _hex_to_rgb(theme.TEXT)
                for r in p.runs:
                    r.font.name = theme.FONT_PPT
                    r.font.size = Pt(body_font_size)
                    r.font.bold = False
                    r.font.color.rgb = _hex_to_rgb(theme.TEXT)


def _render_chart(
    slide: Any,
    slide_spec: SlideSpec,
    figures_by_id: dict[str, FigureSpec],
) -> None:
    """Render native bar chart from FigureSpec filling content area with clean integer axes and data labels."""
    _add_slide_title(slide, slide_spec.title)

    fig = figures_by_id.get(slide_spec.figure_id) if slide_spec.figure_id else None
    if fig is None:
        logger.warning(
            "Figure '%s' referenced by slide '%s' not found.",
            slide_spec.figure_id,
            slide_spec.title,
        )
        _add_missing_figure_placeholder(slide, slide_spec.figure_id)
        return

    labels = fig.labels if fig.labels else ["Default"]
    values = [float(v) for v in fig.values] if fig.values else [0.0]

    chart_data = CategoryChartData()
    chart_data.categories = labels
    series_name = fig.title or slide_spec.title
    chart_data.add_series(series_name, values)

    # Sized to fill the content area
    chart_shape = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1.0),
        Inches(1.8),
        Inches(11.333),
        Inches(4.7),
        chart_data,
    )
    chart = chart_shape.chart

    # No legend for single series
    chart.has_legend = len(chart.series) > 1

    # No chart title duplication: the slide title is the title.
    chart.has_title = False

    val_axis = chart.value_axis
    cat_axis = chart.category_axis

    # If FigureSpec title is distinct from slide title, use as value axis title / caption
    if fig.title and fig.title.strip().lower() != slide_spec.title.strip().lower():
        val_axis.has_title = True
        val_axis.axis_title.text_frame.text = fig.title
        for p in val_axis.axis_title.text_frame.paragraphs:
            p.font.name = theme.FONT_PPT
            p.font.size = Pt(theme.CHART_AXIS_FONT_SIZE)
            p.font.color.rgb = _hex_to_rgb(theme.MUTED)

    # Integer value axis when all values are whole numbers
    is_all_integers = all(abs(v - round(v)) < 1e-6 for v in values)
    if is_all_integers:
        val_axis.major_unit = 1
        val_axis.tick_labels.number_format = "0"
        val_axis.tick_labels.number_format_is_linked = False

    # Axis label fonts >= 12pt
    val_axis.tick_labels.font.name = theme.FONT_PPT
    val_axis.tick_labels.font.size = Pt(theme.CHART_AXIS_FONT_SIZE)
    cat_axis.tick_labels.font.name = theme.FONT_PPT
    cat_axis.tick_labels.font.size = Pt(theme.CHART_AXIS_FONT_SIZE)

    # Light gridlines
    val_axis.has_major_gridlines = True
    try:
        val_axis.major_gridlines.format.line.color.rgb = _hex_to_rgb(theme.TABLE_HEADER_FILL)
    except Exception:
        pass

    # Data labels on
    if chart.plots:
        plot = chart.plots[0]
        plot.has_data_labels = True
        data_labels = plot.data_labels
        data_labels.font.name = theme.FONT_PPT
        data_labels.font.size = Pt(theme.CHART_AXIS_FONT_SIZE)
        data_labels.font.color.rgb = _hex_to_rgb(theme.TEXT)

    # Series bar color
    if len(chart.series) > 0:
        series = chart.series[0]
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = _hex_to_rgb(theme.PRIMARY)


def _add_tail_arrowhead(conn: Any) -> None:
    """Add a:tailEnd triangle arrowhead to connector XML."""
    try:
        ln = conn.line._get_or_add_ln()
        tail = OxmlElement("a:tailEnd")
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
        ln.append(tail)
    except Exception as exc:
        logger.debug("Failed to set tail arrowhead: %s", exc)


def _style_connector(conn: Any) -> None:
    """Apply consistent accent styling to connector line."""
    conn.line.color.rgb = _hex_to_rgb(theme.DIAGRAM_CONNECTOR_COLOR)
    conn.line.width = Pt(1.5)


def _render_diagram(
    slide: Any,
    slide_spec: SlideSpec,
    figures_by_id: dict[str, FigureSpec],
) -> None:
    """
    Render editable rounded rectangles and connectors/arrows in structured grid flow.
    Up to 4 nodes per row with contrasting text, wrapped labels, and clear elbow routing
    for row-wrap and back/feedback edges that never intersect node boxes.
    """
    _add_slide_title(slide, slide_spec.title)

    fig = figures_by_id.get(slide_spec.figure_id) if slide_spec.figure_id else None
    if fig is None or not fig.nodes:
        logger.warning(
            "Diagram figure '%s' referenced by slide '%s' not found or has no nodes.",
            slide_spec.figure_id,
            slide_spec.title,
        )
        _add_missing_figure_placeholder(slide, slide_spec.figure_id)
        return

    num_nodes = len(fig.nodes)
    max_per_row = 4
    num_rows = min(3, max(1, (num_nodes + max_per_row - 1) // max_per_row))

    node_w = Inches(2.1)
    gap_x = Inches(0.7)
    left_start = Inches(1.416)

    if num_rows == 1:
        node_h = Inches(1.2)
        row_y = [Inches(3.4)]
    elif num_rows == 2:
        node_h = Inches(1.1)
        row_y = [Inches(2.2), Inches(4.7)]
    else:
        node_h = Inches(0.9)
        row_y = [Inches(1.9), Inches(3.4), Inches(4.9)]

    node_info: dict[str, dict[str, Any]] = {}

    for i, name in enumerate(fig.nodes):
        r = i // max_per_row
        c = i % max_per_row
        if r >= num_rows:
            break
        x = Emu(int(left_start + c * (node_w + gap_x)))
        y = Emu(int(row_y[r]))
        w_emu = Emu(int(node_w))
        h_emu = Emu(int(node_h))

        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w_emu, h_emu)
        shape.fill.solid()
        shape.fill.fore_color.rgb = _hex_to_rgb(theme.DIAGRAM_NODE_FILL)
        shape.line.color.rgb = _hex_to_rgb(theme.DIAGRAM_NODE_BORDER)
        shape.line.width = Pt(1.5)

        tf = shape.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.08)
        tf.margin_right = Inches(0.08)
        tf.margin_top = Inches(0.05)
        tf.margin_bottom = Inches(0.05)
        tf.clear()

        node_font_size = 14.0 if len(name) > 22 else 16.0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.name = theme.FONT_PPT
        p.font.size = Pt(node_font_size)
        p.font.bold = True
        p.font.color.rgb = _hex_to_rgb(theme.DIAGRAM_NODE_TEXT)

        run = p.add_run()
        run.text = name
        run.font.name = theme.FONT_PPT
        run.font.size = Pt(node_font_size)
        run.font.bold = True
        run.font.color.rgb = _hex_to_rgb(theme.DIAGRAM_NODE_TEXT)

        node_info[name] = {
            "idx": i,
            "row": r,
            "col": c,
            "x": x,
            "y": y,
            "w": w_emu,
            "h": h_emu,
            "shape": shape,
        }

    # Small gap so connectors do not touch or overlap node borders
    gap = Inches(0.06)

    # Route edges
    for src, dst in fig.edges:
        if src not in node_info or dst not in node_info:
            continue

        s_info = node_info[src]
        d_info = node_info[dst]
        s_idx, d_idx = s_info["idx"], d_info["idx"]
        s_row, s_col = s_info["row"], s_info["col"]
        d_row, d_col = d_info["row"], d_info["col"]
        sx, sy, sw, sh = s_info["x"], s_info["y"], s_info["w"], s_info["h"]
        dx, dy, dw, dh = d_info["x"], d_info["y"], d_info["w"], d_info["h"]

        # 1. Back / Feedback edge (target index < source index)
        if d_idx < s_idx:
            if s_row == 1 and d_row == 0:
                # Feedback from row 1 to row 0: route through middle channel
                y_chan = Emu(int(row_y[0] + node_h + (row_y[1] - (row_y[0] + node_h)) // 2))
                c1 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), Emu(int(sy - gap)),
                    Emu(int(sx + sw // 2)), y_chan,
                )
                _style_connector(c1)

                c2 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), y_chan,
                    Emu(int(dx + dw // 2)), y_chan,
                )
                _style_connector(c2)

                c3 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(dx + dw // 2)), y_chan,
                    Emu(int(dx + dw // 2)), Emu(int(dy + dh + gap)),
                )
                _style_connector(c3)
                _add_tail_arrowhead(c3)

            elif s_row == 0 and d_row == 0:
                # Feedback within row 0: route along top margin
                y_top_chan = Emu(int(row_y[0] - Inches(0.35)))
                c1 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), Emu(int(sy - gap)),
                    Emu(int(sx + sw // 2)), y_top_chan,
                )
                _style_connector(c1)

                c2 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), y_top_chan,
                    Emu(int(dx + dw // 2)), y_top_chan,
                )
                _style_connector(c2)

                c3 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(dx + dw // 2)), y_top_chan,
                    Emu(int(dx + dw // 2)), Emu(int(dy - gap)),
                )
                _style_connector(c3)
                _add_tail_arrowhead(c3)

            else:
                # Feedback along bottom margin
                y_bot_chan = Emu(int(row_y[s_row] + node_h + Inches(0.35)))
                c1 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), Emu(int(sy + sh + gap)),
                    Emu(int(sx + sw // 2)), y_bot_chan,
                )
                _style_connector(c1)

                c2 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(sx + sw // 2)), y_bot_chan,
                    Emu(int(dx + dw // 2)), y_bot_chan,
                )
                _style_connector(c2)

                c3 = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(dx + dw // 2)), y_bot_chan,
                    Emu(int(dx + dw // 2)), Emu(int(dy + dh + gap)),
                )
                _style_connector(c3)
                _add_tail_arrowhead(c3)

        # 2. Adjacent nodes in the same row
        elif s_row == d_row and d_col == s_col + 1:
            conn = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(sx + sw + gap)), Emu(int(sy + sh // 2)),
                Emu(int(dx - gap)), Emu(int(dy + dh // 2)),
            )
            _style_connector(conn)
            _add_tail_arrowhead(conn)

        # 3. Row-wrap edge (last node of row to first node of next row)
        elif s_row + 1 == d_row and s_col == 3 and d_col == 0:
            y_chan = Emu(int(row_y[s_row] + node_h + (row_y[d_row] - (row_y[s_row] + node_h)) // 2))
            x_r = Emu(int(sx + sw + Inches(0.35)))
            x_l = Emu(int(dx - Inches(0.35)))

            c1 = slide.shapes.add_connector(
                MSO_CONNECTOR.ELBOW,
                Emu(int(sx + sw + gap)), Emu(int(sy + sh // 2)),
                x_r, y_chan,
            )
            _style_connector(c1)

            c2 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                x_r, y_chan,
                x_l, y_chan,
            )
            _style_connector(c2)

            c3 = slide.shapes.add_connector(
                MSO_CONNECTOR.ELBOW,
                x_l, y_chan,
                Emu(int(dx - gap)), Emu(int(dy + dh // 2)),
            )
            _style_connector(c3)
            _add_tail_arrowhead(c3)

        # 4. Forward cross-row or skip edge
        elif s_row < d_row:
            y_chan = Emu(int(row_y[s_row] + node_h + (row_y[d_row] - (row_y[s_row] + node_h)) // 2))
            c1 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(sx + sw // 2)), Emu(int(sy + sh + gap)),
                Emu(int(sx + sw // 2)), y_chan,
            )
            _style_connector(c1)

            c2 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(sx + sw // 2)), y_chan,
                Emu(int(dx + dw // 2)), y_chan,
            )
            _style_connector(c2)

            c3 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(dx + dw // 2)), y_chan,
                Emu(int(dx + dw // 2)), Emu(int(dy - gap)),
            )
            _style_connector(c3)
            _add_tail_arrowhead(c3)

        else:
            # Fallback for forward skip in same row
            y_top_chan = Emu(int(row_y[s_row] - Inches(0.35)))
            c1 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(sx + sw // 2)), Emu(int(sy - gap)),
                Emu(int(sx + sw // 2)), y_top_chan,
            )
            _style_connector(c1)

            c2 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(sx + sw // 2)), y_top_chan,
                Emu(int(dx + dw // 2)), y_top_chan,
            )
            _style_connector(c2)

            c3 = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT,
                Emu(int(dx + dw // 2)), y_top_chan,
                Emu(int(dx + dw // 2)), Emu(int(dy - gap)),
            )
            _style_connector(c3)
            _add_tail_arrowhead(c3)


def _render_structured_pptx(
    composer_result: ComposerResult,
    output_path: Path,
) -> Path:
    """Render a 16:9 widescreen presentation from StructuredContent SlideSpecs."""
    structured = composer_result.structured
    assert structured is not None

    figures_by_id = {fig.figure_id: fig for fig in structured.figures}

    prs = Presentation()
    prs.slide_width = Inches(theme.SLIDE_WIDTH_INCHES)
    prs.slide_height = Inches(theme.SLIDE_HEIGHT_INCHES)

    blank_layout = _get_blank_layout(prs)

    for slide_idx, slide_spec in enumerate(structured.slides, start=1):
        slide = prs.slides.add_slide(blank_layout)

        layout = slide_spec.layout

        if layout == "title":
            _render_title_or_closing(slide, slide_spec, is_closing=False)
        elif layout == "closing":
            _render_title_or_closing(slide, slide_spec, is_closing=True)
        elif layout == "section_divider":
            _render_section_divider(slide, slide_spec)
        elif layout == "agenda":
            _render_bullets(slide, slide_spec, is_agenda=True)
        elif layout == "bullets":
            _render_bullets(slide, slide_spec, is_agenda=False)
        elif layout == "table":
            _render_table(slide, slide_spec)
        elif layout == "chart":
            _render_chart(slide, slide_spec, figures_by_id)
        elif layout == "diagram":
            _render_diagram(slide, slide_spec, figures_by_id)
        else:
            # Fallback for unexpected layout string
            _render_bullets(slide, slide_spec, is_agenda=False)

        # Footer on every non-title slide: slide number in 12pt, MUTED color, bottom-right
        if layout not in ("title", "closing"):
            footer_box = slide.shapes.add_textbox(
                Inches(11.0), Inches(6.8), Inches(1.8), Inches(0.4)
            )
            fp = footer_box.text_frame.paragraphs[0]
            fp.text = str(slide_idx)
            fp.font.name = theme.FONT_PPT
            fp.font.size = Pt(theme.FOOTER_FONT_SIZE)
            fp.font.color.rgb = _hex_to_rgb(theme.MUTED)
            fp.alignment = PP_ALIGN.RIGHT

        # Speaker notes
        if slide_spec.notes:
            slide.notes_slide.notes_text_frame.text = slide_spec.notes

    prs.save(output_path)
    return output_path


def render_pptx(
    composer_result: ComposerResult,
    output_path: str | Path,
) -> Path:
    """
    Render a ComposerResult into a PPTX presentation.

    The renderer only formats the content supplied by the Composer.
    It does not generate or modify research content.
    """
    output_path = Path(output_path)

    if output_path.suffix.lower() != ".pptx":
        raise ValueError("Output path must have a .pptx extension.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # If structured content with slides is present, render 16:9 theme presentation
    if (
        composer_result.structured is not None
        and composer_result.structured.slides
    ):
        return _render_structured_pptx(composer_result, output_path)

    # Fallback to legacy 4:3 template layout
    presentation = Presentation()

    # Title slide
    title_slide = presentation.slides.add_slide(
        presentation.slide_layouts[0]
    )

    title_slide.shapes.title.text = composer_result.title

    if len(title_slide.placeholders) > 1:
        subtitle = title_slide.placeholders[1]
        subtitle.text = ""

    # Content slides
    for section_name, section_content in composer_result.sections.items():
        slide = presentation.slides.add_slide(
            presentation.slide_layouts[1]
        )

        slide.shapes.title.text = section_name

        body = slide.placeholders[1]
        body.text = section_content

        # Keep body text readable
        for paragraph in body.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(20)

    presentation.save(output_path)

    return output_path