import logging
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Pt, RGBColor

from backend.agents.output_renderer import theme
from backend.schemas.schemas import (
    ComposerResult,
    ContentBlock,
    DocSection,
    FigureSpec,
    OutputType,
)

logger = logging.getLogger(__name__)

# Printable content width on A4 page with 2.54 cm margins:
# 21.0 cm - 2 * 2.54 cm = 15.92 cm
PRINTABLE_WIDTH_CM = 15.92

UNNUMBERED_HEADINGS = {
    "abstract",
    "abstracts",
    "limitations",
    "acknowledgments",
    "acknowledgements",
    "references",
    "front matter",
}


def _hex_to_rgb(hex_str: str) -> RGBColor:
    """Convert a hex color string (e.g. '#1E3A8A' or '1E3A8A') to docx RGBColor."""
    clean = hex_str.lstrip("#")
    return RGBColor(int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _set_section_columns(section, num_cols: int, space_cm: float = 0.6) -> None:
    """Set the number of columns and spacing on a section using direct OOXML."""
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    space_dxa = int(round(space_cm / 2.54 * 1440))
    if cols is not None:
        cols.set(qn("w:num"), str(num_cols))
        if num_cols > 1:
            cols.set(qn("w:space"), str(space_dxa))
        elif qn("w:space") in cols.attrib:
            del cols.attrib[qn("w:space")]
    else:
        if num_cols > 1:
            cols_xml = parse_xml(f'<w:cols {nsdecls("w")} w:num="{num_cols}" w:space="{space_dxa}"/>')
        else:
            cols_xml = parse_xml(f'<w:cols {nsdecls("w")} w:num="1"/>')
        sectPr.append(cols_xml)


def _render_docx_fallback(
    composer_result: ComposerResult,
    output_path: Path,
) -> Path:
    """
    Render unstructured ComposerResult fallback exactly matching previous behavior.
    """
    document = Document()

    title = document.add_heading(composer_result.title, level=0)
    for run in title.runs:
        run.font.size = Pt(20)

    for section_name, section_content in composer_result.sections.items():
        document.add_heading(section_name, level=1)
        if section_content:
            paragraph = document.add_paragraph(section_content)
            for run in paragraph.runs:
                run.font.size = Pt(11)

    document.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Modern (Executive Summary) Layout Helpers
# ---------------------------------------------------------------------------

def _configure_modern_page_and_styles(document: Document) -> None:
    """Configure A4 geometry, 2.54 cm margins, and core typography styles for Executive Summary."""
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(theme.DOCX_PAGE_MARGIN_CM)
    section.bottom_margin = Cm(theme.DOCX_PAGE_MARGIN_CM)
    section.left_margin = Cm(theme.DOCX_PAGE_MARGIN_CM)
    section.right_margin = Cm(theme.DOCX_PAGE_MARGIN_CM)
    _set_section_columns(section, num_cols=1)

    styles = document.styles

    # 1. Normal (body)
    normal = styles["Normal"]
    normal.font.name = theme.FONT_WORD
    normal.font.size = Pt(theme.FONT_SIZE_BODY)
    normal.font.color.rgb = _hex_to_rgb(theme.TEXT)
    normal.paragraph_format.line_spacing = theme.SPACING_LINE_HEIGHT
    normal.paragraph_format.space_after = Pt(theme.SPACING_PARAGRAPH_AFTER)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 2. Title
    if "Title" in styles:
        title_style = styles["Title"]
    else:
        title_style = styles.add_style("Title", WD_STYLE_TYPE.PARAGRAPH)
    title_style.font.name = theme.FONT_WORD
    title_style.font.size = Pt(22.0)
    title_style.font.bold = True
    title_style.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
    title_style.paragraph_format.keep_with_next = True
    title_style.paragraph_format.space_before = Pt(0)
    title_style.paragraph_format.space_after = Pt(8)

    # 3. Heading 1
    if "Heading 1" in styles:
        h1 = styles["Heading 1"]
    else:
        h1 = styles.add_style("Heading 1", WD_STYLE_TYPE.PARAGRAPH)
    h1.font.name = theme.FONT_WORD
    h1.font.size = Pt(theme.FONT_SIZE_H1)
    h1.font.bold = True
    h1.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
    h1.paragraph_format.keep_with_next = True
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(6)

    # 4. Heading 2
    if "Heading 2" in styles:
        h2 = styles["Heading 2"]
    else:
        h2 = styles.add_style("Heading 2", WD_STYLE_TYPE.PARAGRAPH)
    h2.font.name = theme.FONT_WORD
    h2.font.size = Pt(theme.FONT_SIZE_H2)
    h2.font.bold = True
    h2.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
    h2.paragraph_format.keep_with_next = True
    h2.paragraph_format.space_before = Pt(10)
    h2.paragraph_format.space_after = Pt(4)

    # 5. Heading 3
    if "Heading 3" in styles:
        h3 = styles["Heading 3"]
    else:
        h3 = styles.add_style("Heading 3", WD_STYLE_TYPE.PARAGRAPH)
    h3.font.name = theme.FONT_WORD
    h3.font.size = Pt(12)
    h3.font.bold = True
    h3.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
    h3.paragraph_format.keep_with_next = True
    h3.paragraph_format.space_before = Pt(8)
    h3.paragraph_format.space_after = Pt(2)

    # 6. Caption
    if "Caption" in styles:
        caption_style = styles["Caption"]
    else:
        caption_style = styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)
    caption_style.font.name = theme.FONT_WORD
    caption_style.font.size = Pt(theme.FONT_SIZE_CAPTION)
    caption_style.font.italic = True
    caption_style.font.color.rgb = _hex_to_rgb(theme.MUTED)
    caption_style.paragraph_format.keep_with_next = True
    caption_style.paragraph_format.space_before = Pt(6)
    caption_style.paragraph_format.space_after = Pt(4)

    # 7. References
    if "References" in styles:
        ref_style = styles["References"]
    else:
        ref_style = styles.add_style("References", WD_STYLE_TYPE.PARAGRAPH)
    ref_style.font.name = theme.FONT_WORD
    ref_style.font.size = Pt(theme.FONT_SIZE_REFERENCES)
    ref_style.font.color.rgb = _hex_to_rgb(theme.TEXT)
    ref_style.paragraph_format.line_spacing = theme.SPACING_LINE_HEIGHT
    ref_style.paragraph_format.space_before = Pt(0)
    ref_style.paragraph_format.space_after = Pt(4)
    ref_style.paragraph_format.left_indent = Inches(0.5)
    ref_style.paragraph_format.first_line_indent = Inches(-0.5)

    # 8. List Bullet
    if "List Bullet" in styles:
        bullet_style = styles["List Bullet"]
        bullet_style.font.name = theme.FONT_WORD
        bullet_style.font.size = Pt(theme.FONT_SIZE_BODY)
        bullet_style.font.color.rgb = _hex_to_rgb(theme.TEXT)
        bullet_style.paragraph_format.line_spacing = theme.SPACING_LINE_HEIGHT
        bullet_style.paragraph_format.space_before = Pt(0)
        bullet_style.paragraph_format.space_after = Pt(3)


def _setup_modern_header_and_footer(document: Document, title: str) -> None:
    """Setup right-aligned document header (page 2+) and centered Page X of Y footer."""
    section = document.sections[0]
    section.different_first_page_header_footer = True

    short_title = title.strip()
    if len(short_title) > 48:
        short_title = short_title[:45].rstrip() + "..."

    # Header on pages 2+
    header = section.header
    hp = header.paragraphs[0]
    hp.text = ""
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hrun = hp.add_run(short_title)
    hrun.font.name = theme.FONT_WORD
    hrun.font.size = Pt(theme.FONT_SIZE_HEADER)
    hrun.font.color.rgb = _hex_to_rgb(theme.MUTED)

    # First page header is empty
    first_header = section.first_page_header
    if first_header.paragraphs:
        first_header.paragraphs[0].text = ""

    # Footer for pages
    for ftr in (section.footer, section.first_page_footer):
        fp = ftr.paragraphs[0]
        fp.text = ""
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

        r1 = fp.add_run("Page ")
        r1.font.name = theme.FONT_WORD
        r1.font.size = Pt(theme.FONT_SIZE_FOOTER)
        r1.font.color.rgb = _hex_to_rgb(theme.MUTED)

        # Field: PAGE
        fld_page = parse_xml(
            r'<w:fldSimple %s w:instr="PAGE">'
            r'<w:r>'
            r'<w:rPr>'
            r'<w:rFonts w:ascii="%s" w:hAnsi="%s"/>'
            r'<w:sz w:val="%s"/>'
            r'<w:color w:val="%s"/>'
            r'</w:rPr>'
            r'<w:t>1</w:t>'
            r'</w:r>'
            r'</w:fldSimple>'
            % (
                nsdecls("w"),
                theme.FONT_WORD,
                theme.FONT_WORD,
                str(int(theme.FONT_SIZE_FOOTER * 2)),
                theme.MUTED.lstrip("#"),
            )
        )
        fp._p.append(fld_page)

        r2 = fp.add_run(" of ")
        r2.font.name = theme.FONT_WORD
        r2.font.size = Pt(theme.FONT_SIZE_FOOTER)
        r2.font.color.rgb = _hex_to_rgb(theme.MUTED)

        # Field: NUMPAGES
        fld_numpages = parse_xml(
            r'<w:fldSimple %s w:instr="NUMPAGES">'
            r'<w:r>'
            r'<w:rPr>'
            r'<w:rFonts w:ascii="%s" w:hAnsi="%s"/>'
            r'<w:sz w:val="%s"/>'
            r'<w:color w:val="%s"/>'
            r'</w:rPr>'
            r'<w:t>1</w:t>'
            r'</w:r>'
            r'</w:fldSimple>'
            % (
                nsdecls("w"),
                theme.FONT_WORD,
                theme.FONT_WORD,
                str(int(theme.FONT_SIZE_FOOTER * 2)),
                theme.MUTED.lstrip("#"),
            )
        )
        fp._p.append(fld_numpages)


def _add_accent_rule(document: Document, space_after_pt: int = 14) -> None:
    """Insert a thin accent horizontal rule using paragraph bottom border."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(space_after_pt)
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(
        r'<w:pBdr %s>'
        r'  <w:bottom w:val="single" w:sz="12" w:space="1" w:color="%s"/>'
        r'</w:pBdr>' % (nsdecls("w"), theme.ACCENT.lstrip("#"))
    )
    pPr.append(pBdr)


def _render_modern_table(
    document: Document,
    table_header: list[str],
    table_rows: list[list[str]],
    caption_text: Optional[str] = None,
) -> None:
    """Render a native Word table with modern styling (shaded header, striped rows, thin borders)."""
    if caption_text:
        cp = document.add_paragraph(caption_text, style="Caption")
        cp.paragraph_format.keep_with_next = True

    num_cols = len(table_header) if table_header else (len(table_rows[0]) if table_rows else 1)
    total_rows = (1 if table_header else 0) + len(table_rows)

    tbl = document.add_table(rows=total_rows, cols=num_cols)
    tblPr = tbl._tbl.tblPr

    existing_borders = tblPr.find(qn("w:tblBorders"))
    if existing_borders is not None:
        tblPr.remove(existing_borders)
    tblBorders = parse_xml(
        r'<w:tblBorders %s>'
        r'  <w:top w:val="single" w:sz="6" w:space="0" w:color="%s"/>'
        r'  <w:left w:val="none"/>'
        r'  <w:bottom w:val="single" w:sz="8" w:space="0" w:color="%s"/>'
        r'  <w:right w:val="none"/>'
        r'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="%s"/>'
        r'  <w:insideV w:val="none"/>'
        r'</w:tblBorders>'
        % (
            nsdecls("w"),
            theme.DOCX_TABLE_BORDER_HEADER_BOTTOM.lstrip("#"),
            theme.DOCX_TABLE_BORDER_HEADER_BOTTOM.lstrip("#"),
            theme.DOCX_TABLE_BORDER_COLOR.lstrip("#"),
        )
    )
    tblPr.append(tblBorders)

    existing_mar = tblPr.find(qn("w:tblCellMar"))
    if existing_mar is not None:
        tblPr.remove(existing_mar)
    tblCellMar = parse_xml(
        r'<w:tblCellMar %s>'
        r'  <w:top w:w="120" w:type="dxa"/>'
        r'  <w:bottom w:w="120" w:type="dxa"/>'
        r'  <w:left w:w="160" w:type="dxa"/>'
        r'  <w:right w:w="160" w:type="dxa"/>'
        r'</w:tblCellMar>' % nsdecls("w")
    )
    tblPr.append(tblCellMar)

    max_lens: list[int] = []
    for c in range(num_cols):
        h_len = len(str(table_header[c])) if c < len(table_header) else 0
        r_lens = [len(str(row[c])) for row in table_rows if c < len(row)]
        col_max = max([h_len] + r_lens) if r_lens else h_len
        max_lens.append(max(col_max, 4))

    total_weight = sum(max_lens) or 1
    col_widths = [Cm(round(PRINTABLE_WIDTH_CM * (l / total_weight), 2)) for l in max_lens]

    current_row_idx = 0
    if table_header:
        header_row = tbl.rows[0]
        trPr = header_row._tr.get_or_add_trPr()
        trPr.append(parse_xml(r'<w:tblHeader %s/>' % nsdecls("w")))
        trPr.append(parse_xml(r'<w:cantSplit %s/>' % nsdecls("w")))

        for c_idx, h_text in enumerate(table_header):
            cell = header_row.cells[c_idx]
            tcPr = cell._tc.get_or_add_tcPr()
            tcPr.append(parse_xml(r'<w:shd %s w:fill="%s"/>' % (nsdecls("w"), theme.TABLE_HEADER_FILL.lstrip("#"))))
            p = cell.paragraphs[0]
            p.text = str(h_text)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            if p.runs:
                run = p.runs[0]
                run.font.name = theme.FONT_WORD
                run.font.size = Pt(10)
                run.font.bold = True
                run.font.color.rgb = _hex_to_rgb(theme.PRIMARY)
        current_row_idx += 1

    for r_idx, row_data in enumerate(table_rows):
        row = tbl.rows[current_row_idx + r_idx]
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(r'<w:cantSplit %s/>' % nsdecls("w")))

        is_striped = (r_idx % 2 == 1)
        for c_idx, cell_data in enumerate(row_data):
            if c_idx >= num_cols:
                break
            cell = row.cells[c_idx]
            if is_striped:
                tcPr = cell._tc.get_or_add_tcPr()
                tcPr.append(parse_xml(r'<w:shd %s w:fill="%s"/>' % (nsdecls("w"), theme.TABLE_STRIPE_FILL.lstrip("#"))))

            p = cell.paragraphs[0]
            p.text = str(cell_data)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            if p.runs:
                run = p.runs[0]
                run.font.name = theme.FONT_WORD
                run.font.size = Pt(10)
                run.font.color.rgb = _hex_to_rgb(theme.TEXT)

    for row in tbl.rows:
        for idx, width in enumerate(col_widths):
            if idx < len(row.cells):
                row.cells[idx].width = width
    for idx, width in enumerate(col_widths):
        if idx < len(tbl.columns):
            tbl.columns[idx].width = width

    if caption_text:
        spacer = document.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(theme.SPACING_PARAGRAPH_AFTER)


def _render_callout_block(document: Document, block: ContentBlock) -> None:
    """Render a single-cell callout table shaded with theme.CALLOUT_FILL and accent left border."""
    tbl = document.add_table(rows=1, cols=1)
    tblPr = tbl._tbl.tblPr

    existing_borders = tblPr.find(qn("w:tblBorders"))
    if existing_borders is not None:
        tblPr.remove(existing_borders)

    tblBorders = parse_xml(
        r'<w:tblBorders %s>'
        r'  <w:top w:val="none"/>'
        r'  <w:left w:val="single" w:sz="%s" w:space="0" w:color="%s"/>'
        r'  <w:bottom w:val="none"/>'
        r'  <w:right w:val="none"/>'
        r'  <w:insideH w:val="none"/>'
        r'  <w:insideV w:val="none"/>'
        r'</w:tblBorders>'
        % (
            nsdecls("w"),
            theme.DOCX_CALLOUT_BORDER_SIZE,
            theme.DOCX_CALLOUT_BORDER_COLOR.lstrip("#"),
        )
    )
    tblPr.append(tblBorders)

    existing_mar = tblPr.find(qn("w:tblCellMar"))
    if existing_mar is not None:
        tblPr.remove(existing_mar)
    tblCellMar = parse_xml(
        r'<w:tblCellMar %s>'
        r'  <w:top w:w="160" w:type="dxa"/>'
        r'  <w:bottom w:w="160" w:type="dxa"/>'
        r'  <w:left w:w="240" w:type="dxa"/>'
        r'  <w:right w:w="200" w:type="dxa"/>'
        r'</w:tblCellMar>' % nsdecls("w")
    )
    tblPr.append(tblCellMar)

    cell = tbl.cell(0, 0)
    cell.width = Cm(PRINTABLE_WIDTH_CM)
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(r'<w:shd %s w:fill="%s"/>' % (nsdecls("w"), theme.CALLOUT_FILL.lstrip("#"))))

    trPr = tbl.rows[0]._tr.get_or_add_trPr()
    trPr.append(parse_xml(r'<w:cantSplit %s/>' % nsdecls("w")))

    p = cell.paragraphs[0]
    p.text = block.text or ""
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = theme.SPACING_LINE_HEIGHT
    if p.runs:
        run = p.runs[0]
        run.font.name = theme.FONT_WORD
        run.font.size = Pt(10.5)
        run.font.color.rgb = _hex_to_rgb(theme.TEXT)

    spacer = document.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(theme.SPACING_PARAGRAPH_AFTER)


def _render_key_numbers_block(document: Document, block: ContentBlock) -> None:
    """Render single-row table of 2-4 cells formatted 'value :: label'."""
    items = block.items
    if not items:
        return

    num_cells = min(max(len(items), 1), 6)
    tbl = document.add_table(rows=1, cols=num_cells)
    tblPr = tbl._tbl.tblPr

    existing_borders = tblPr.find(qn("w:tblBorders"))
    if existing_borders is not None:
        tblPr.remove(existing_borders)
    tblBorders = parse_xml(
        r'<w:tblBorders %s>'
        r'  <w:top w:val="none"/>'
        r'  <w:left w:val="none"/>'
        r'  <w:bottom w:val="none"/>'
        r'  <w:right w:val="none"/>'
        r'  <w:insideH w:val="none"/>'
        r'  <w:insideV w:val="none"/>'
        r'</w:tblBorders>' % nsdecls("w")
    )
    tblPr.append(tblBorders)

    col_width = Cm(round(PRINTABLE_WIDTH_CM / num_cells, 2))

    for idx, item in enumerate(items[:num_cells]):
        cell = tbl.cell(0, idx)
        cell.width = col_width

        if "::" in item:
            val_text, lbl_text = item.split("::", 1)
        else:
            val_text, lbl_text = item, ""

        val_text = val_text.strip()
        lbl_text = lbl_text.strip()

        p1 = cell.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p1.paragraph_format.space_before = Pt(4)
        p1.paragraph_format.space_after = Pt(1)
        r1 = p1.add_run(val_text)
        r1.font.name = theme.FONT_WORD
        r1.font.size = Pt(theme.FONT_SIZE_KEY_NUMBER)
        r1.font.bold = True
        r1.font.color.rgb = _hex_to_rgb(theme.PRIMARY)

        if lbl_text:
            p2 = cell.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.space_before = Pt(0)
            p2.paragraph_format.space_after = Pt(4)
            r2 = p2.add_run(lbl_text)
            r2.font.name = theme.FONT_WORD
            r2.font.size = Pt(9.0)
            r2.font.color.rgb = _hex_to_rgb(theme.MUTED)

    spacer = document.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(theme.SPACING_PARAGRAPH_AFTER)


# ---------------------------------------------------------------------------
# Academic (ACL-Style) Layout Helpers
# ---------------------------------------------------------------------------

def _configure_academic_page_and_styles(document: Document) -> None:
    """Configure A4 geometry, 2.5 cm margins, and Times New Roman academic typography."""
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
    section.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
    section.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
    section.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
    _set_section_columns(section, num_cols=1)

    styles = document.styles

    # 0. Title (bold 15pt, centered, keep_with_next)
    if "Title" in styles:
        title_style = styles["Title"]
    else:
        title_style = styles.add_style("Title", WD_STYLE_TYPE.PARAGRAPH)
    title_style.font.name = theme.FONT_ACADEMIC
    title_style.font.size = Pt(theme.FONT_SIZE_ACADEMIC_TITLE)
    title_style.font.bold = True
    title_style.font.color.rgb = RGBColor(0, 0, 0)
    title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_style.paragraph_format.first_line_indent = Pt(0)
    title_style.paragraph_format.left_indent = Pt(0)
    title_style.paragraph_format.right_indent = Pt(0)
    title_style.paragraph_format.space_before = Pt(0)
    title_style.paragraph_format.space_after = Pt(8)
    title_style.paragraph_format.keep_with_next = True

    # 1. Normal (body: 11pt, justified, single line spacing, 0 space after)
    normal = styles["Normal"]
    normal.font.name = theme.FONT_ACADEMIC
    normal.font.size = Pt(theme.FONT_SIZE_ACADEMIC_BODY)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 1.0
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 2. Heading 1 (bold 12pt, space before 10pt, after 4pt, keep_with_next)
    if "Heading 1" in styles:
        h1 = styles["Heading 1"]
    else:
        h1 = styles.add_style("Heading 1", WD_STYLE_TYPE.PARAGRAPH)
    h1.font.name = theme.FONT_ACADEMIC
    h1.font.size = Pt(theme.FONT_SIZE_ACADEMIC_H1)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor(0, 0, 0)
    h1.paragraph_format.keep_with_next = True
    h1.paragraph_format.space_before = Pt(10)
    h1.paragraph_format.space_after = Pt(4)
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 3. Heading 2 (bold 11pt, space before 6pt, after 4pt, keep_with_next)
    if "Heading 2" in styles:
        h2 = styles["Heading 2"]
    else:
        h2 = styles.add_style("Heading 2", WD_STYLE_TYPE.PARAGRAPH)
    h2.font.name = theme.FONT_ACADEMIC
    h2.font.size = Pt(theme.FONT_SIZE_ACADEMIC_H2)
    h2.font.bold = True
    h2.font.color.rgb = RGBColor(0, 0, 0)
    h2.paragraph_format.keep_with_next = True
    h2.paragraph_format.space_before = Pt(6)
    h2.paragraph_format.space_after = Pt(4)
    h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 4. Heading 3 (bold italic 11pt, space before 4pt, after 4pt, keep_with_next)
    if "Heading 3" in styles:
        h3 = styles["Heading 3"]
    else:
        h3 = styles.add_style("Heading 3", WD_STYLE_TYPE.PARAGRAPH)
    h3.font.name = theme.FONT_ACADEMIC
    h3.font.size = Pt(theme.FONT_SIZE_ACADEMIC_H3)
    h3.font.bold = True
    h3.font.italic = True
    h3.font.color.rgb = RGBColor(0, 0, 0)
    h3.paragraph_format.keep_with_next = True
    h3.paragraph_format.space_before = Pt(4)
    h3.paragraph_format.space_after = Pt(4)
    h3.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 5. Caption (10pt, keep_with_next)
    if "Caption" in styles:
        caption_style = styles["Caption"]
    else:
        caption_style = styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)
    caption_style.font.name = theme.FONT_ACADEMIC
    caption_style.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
    caption_style.font.italic = False
    caption_style.font.color.rgb = RGBColor(0, 0, 0)
    caption_style.paragraph_format.keep_with_next = True
    caption_style.paragraph_format.space_before = Pt(6)
    caption_style.paragraph_format.space_after = Pt(4)

    # 6. References (10pt, left-aligned, hanging indent 0.5 cm, 2pt space after)
    if "References" in styles:
        ref_style = styles["References"]
    else:
        ref_style = styles.add_style("References", WD_STYLE_TYPE.PARAGRAPH)
    ref_style.font.name = theme.FONT_ACADEMIC
    ref_style.font.size = Pt(theme.FONT_SIZE_ACADEMIC_REFERENCES)
    ref_style.font.color.rgb = RGBColor(0, 0, 0)
    ref_style.paragraph_format.line_spacing = 1.0
    ref_style.paragraph_format.space_before = Pt(0)
    ref_style.paragraph_format.space_after = Pt(2)
    ref_style.paragraph_format.left_indent = Cm(theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
    ref_style.paragraph_format.first_line_indent = Cm(-theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
    ref_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 7. List Bullet (11pt, compact spacing)
    if "List Bullet" in styles:
        bullet_style = styles["List Bullet"]
        bullet_style.font.name = theme.FONT_ACADEMIC
        bullet_style.font.size = Pt(theme.FONT_SIZE_ACADEMIC_BODY)
        bullet_style.font.color.rgb = RGBColor(0, 0, 0)
        bullet_style.paragraph_format.line_spacing = 1.0
        bullet_style.paragraph_format.space_before = Pt(0)
        bullet_style.paragraph_format.space_after = Pt(2)


def _setup_academic_footer(document: Document) -> None:
    """Setup centered 10pt real PAGE field footer with no header for Academic layout."""
    section = document.sections[0]
    section.different_first_page_header_footer = False

    header = section.header
    if header.paragraphs:
        header.paragraphs[0].text = ""

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    fld_page = parse_xml(
        r'<w:fldSimple %s w:instr="PAGE">'
        r'<w:r>'
        r'<w:rPr>'
        r'<w:rFonts w:ascii="%s" w:hAnsi="%s"/>'
        r'<w:sz w:val="%s"/>'
        r'</w:rPr>'
        r'<w:t>1</w:t>'
        r'</w:r>'
        r'</w:fldSimple>'
        % (
            nsdecls("w"),
            theme.FONT_ACADEMIC,
            theme.FONT_ACADEMIC,
            str(int(theme.FONT_SIZE_ACADEMIC_FOOTER * 2)),
        )
    )
    fp._p.append(fld_page)


def _render_academic_table(
    document: Document,
    table_header: list[str],
    table_rows: list[list[str]],
    caption_text: Optional[str] = None,
    width_cm: float = theme.DOCX_ACADEMIC_COL_WIDTH_CM,
) -> None:
    """
    Render an academic table (booktabs style):
    - Caption ABOVE as 'Table n: text' (10pt, keep_with_next)
    - Horizontal rules only (thick top and bottom rule, thin rule under header)
    - No vertical lines, no fills
    - Header bold, 10pt text, tblHeader, cantSplit
    - Data rows 10pt text, cantSplit
    - Proportional column widths
    """
    if caption_text:
        cp = document.add_paragraph(style="Caption")
        cp.paragraph_format.keep_with_next = True
        cp.paragraph_format.space_before = Pt(6)
        cp.paragraph_format.space_after = Pt(3)
        cp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if ": " in caption_text:
            tbl_label, tbl_desc = caption_text.split(": ", 1)
            r1 = cp.add_run(f"{tbl_label}: ")
            r1.font.name = theme.FONT_ACADEMIC
            r1.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
            r1.font.bold = True
            r2 = cp.add_run(tbl_desc)
            r2.font.name = theme.FONT_ACADEMIC
            r2.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
        else:
            r = cp.add_run(caption_text)
            r.font.name = theme.FONT_ACADEMIC
            r.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
            r.font.bold = True

    num_cols = len(table_header) if table_header else (len(table_rows[0]) if table_rows else 1)
    total_rows = (1 if table_header else 0) + len(table_rows)

    tbl = document.add_table(rows=total_rows, cols=num_cols)
    tblPr = tbl._tbl.tblPr

    # 1. Booktabs horizontal borders: thick top (sz="12") and bottom (sz="12"), no vertical borders
    existing_borders = tblPr.find(qn("w:tblBorders"))
    if existing_borders is not None:
        tblPr.remove(existing_borders)
    tblBorders = parse_xml(
        r'<w:tblBorders %s>'
        r'  <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
        r'  <w:left w:val="none"/>'
        r'  <w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
        r'  <w:right w:val="none"/>'
        r'  <w:insideH w:val="none"/>'
        r'  <w:insideV w:val="none"/>'
        r'</w:tblBorders>' % nsdecls("w")
    )
    tblPr.append(tblBorders)

    # 2. Compact cell margins
    existing_mar = tblPr.find(qn("w:tblCellMar"))
    if existing_mar is not None:
        tblPr.remove(existing_mar)
    tblCellMar = parse_xml(
        r'<w:tblCellMar %s>'
        r'  <w:top w:w="80" w:type="dxa"/>'
        r'  <w:bottom w:w="80" w:type="dxa"/>'
        r'  <w:left w:w="120" w:type="dxa"/>'
        r'  <w:right w:w="120" w:type="dxa"/>'
        r'</w:tblCellMar>' % nsdecls("w")
    )
    tblPr.append(tblCellMar)

    max_lens: list[int] = []
    for c in range(num_cols):
        h_len = len(str(table_header[c])) if c < len(table_header) else 0
        r_lens = [len(str(row[c])) for row in table_rows if c < len(row)]
        col_max = max([h_len] + r_lens) if r_lens else h_len
        max_lens.append(max(col_max, 4))

    total_weight = sum(max_lens) or 1
    col_widths = [Cm(round(width_cm * (l / total_weight), 2)) for l in max_lens]

    current_row_idx = 0
    if table_header:
        header_row = tbl.rows[0]
        trPr = header_row._tr.get_or_add_trPr()
        trPr.append(parse_xml(r'<w:tblHeader %s/>' % nsdecls("w")))
        trPr.append(parse_xml(r'<w:cantSplit %s/>' % nsdecls("w")))

        for c_idx, h_text in enumerate(table_header):
            cell = header_row.cells[c_idx]
            tcPr = cell._tc.get_or_add_tcPr()
            # Thin rule under the header
            tcBorders = parse_xml(
                r'<w:tcBorders %s>'
                r'  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
                r'</w:tcBorders>' % nsdecls("w")
            )
            tcPr.append(tcBorders)

            p = cell.paragraphs[0]
            p.text = str(h_text)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            if p.runs:
                run = p.runs[0]
                run.font.name = theme.FONT_ACADEMIC
                run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_TABLE)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)
        current_row_idx += 1

    for r_idx, row_data in enumerate(table_rows):
        row = tbl.rows[current_row_idx + r_idx]
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(r'<w:cantSplit %s/>' % nsdecls("w")))

        for c_idx, cell_data in enumerate(row_data):
            if c_idx >= num_cols:
                break
            cell = row.cells[c_idx]
            p = cell.paragraphs[0]
            p.text = str(cell_data)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            if p.runs:
                run = p.runs[0]
                run.font.name = theme.FONT_ACADEMIC
                run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_TABLE)
                run.font.color.rgb = RGBColor(0, 0, 0)

    for row in tbl.rows:
        for idx, width in enumerate(col_widths):
            if idx < len(row.cells):
                row.cells[idx].width = width
    for idx, width in enumerate(col_widths):
        if idx < len(tbl.columns):
            tbl.columns[idx].width = width

    if caption_text:
        spacer = document.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(4)


def _render_academic_callout(document: Document, block: ContentBlock) -> None:
    """Render callout as a plain indented italic paragraph (never a shaded box)."""
    p = document.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(block.text or "")
    run.font.name = theme.FONT_ACADEMIC
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)


def _render_academic_key_numbers(document: Document, block: ContentBlock) -> None:
    """Render key numbers as a simple plain text line (never a shaded box)."""
    items = block.items
    if not items:
        return
    items_text = "   |   ".join(item.replace("::", ":") for item in items)
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(items_text)
    run.font.name = theme.FONT_ACADEMIC
    run.font.size = Pt(10.0)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)


# ---------------------------------------------------------------------------
# Figure Block Renderer
# ---------------------------------------------------------------------------

def _render_figure_block(
    document: Document,
    block: ContentBlock,
    figure_map: dict[str, FigureSpec],
    figure_counter: int,
    is_academic: bool = False,
    width_cm: float = theme.DOCX_ACADEMIC_COL_WIDTH_CM,
) -> int:
    """
    Render FigureSpec data as a data table plus caption BELOW: 'Figure n: text'.
    Returns updated figure_counter.
    """
    fig = figure_map.get(block.figure_id) if block.figure_id else None

    if fig is None:
        logger.warning("FigureSpec not found for figure_id: %s", block.figure_id)
        p = document.add_paragraph()
        run = p.add_run(f"[Figure placeholder: {block.figure_id or 'unknown'} not found]")
        run.font.italic = True
        run.font.color.rgb = _hex_to_rgb(theme.MUTED)
        return figure_counter

    figure_counter += 1
    caption_label = block.caption or fig.title

    if fig.labels and fig.values:
        header = ["Item / Category", "Value"]
        rows = [
            [str(l), str(int(v) if isinstance(v, (int, float)) and v == int(v) else v)]
            for l, v in zip(fig.labels, fig.values)
        ]
    elif fig.edges:
        header = ["Source Component", "Target Component"]
        rows = [[str(src), str(dst)] for src, dst in fig.edges]
    elif fig.nodes:
        header = ["Step", "Workflow Component"]
        rows = [[str(i + 1), str(node)] for i, node in enumerate(fig.nodes)]
    else:
        header = ["Component", "Description"]
        rows = [[fig.title, "Visual figure diagram"]]

    # 1. Render figure content FIRST (caption is BELOW figure content)
    if is_academic:
        _render_academic_table(
            document=document,
            table_header=header,
            table_rows=rows,
            caption_text=None,
            width_cm=width_cm,
        )
    else:
        _render_modern_table(
            document=document,
            table_header=header,
            table_rows=rows,
            caption_text=None,
        )

    # 2. Render caption paragraph AFTER figure content
    cp = document.add_paragraph(style="Caption")
    cp.paragraph_format.keep_with_next = False
    cp.paragraph_format.space_before = Pt(3)
    cp.paragraph_format.space_after = Pt(8)

    if is_academic:
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = cp.add_run(f"Figure {figure_counter}: ")
        r1.font.name = theme.FONT_ACADEMIC
        r1.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
        r1.font.bold = True
        r2 = cp.add_run(caption_label)
        r2.font.name = theme.FONT_ACADEMIC
        r2.font.size = Pt(theme.FONT_SIZE_ACADEMIC_CAPTION)
        r2.font.bold = False
    else:
        cp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = cp.add_run(f"Figure {figure_counter}: {caption_label}")
        r.font.name = theme.FONT_WORD
        r.font.size = Pt(theme.FONT_SIZE_CAPTION)
        r.font.italic = True
        r.font.color.rgb = _hex_to_rgb(theme.MUTED)

    return figure_counter


# ---------------------------------------------------------------------------
# Main render_docx Entrypoint
# ---------------------------------------------------------------------------

def render_docx(
    composer_result: ComposerResult,
    output_path: str | Path,
) -> Path:
    """
    Render a ComposerResult into a DOCX document.

    If composer_result.structured has sections, renders from them using:
    - ACL-style 2-column conference paper layout for Research Paper and Literature Survey.
    - Clean 1-column modern executive brief for Executive Summary.
    Otherwise keeps the original text dump behavior as a safe fallback.
    """
    output_path = Path(output_path)

    if output_path.suffix.lower() != ".docx":
        raise ValueError("Output path must have a .docx extension.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Safe fallback if structured content is missing
    if not composer_result.structured or not composer_result.structured.sections:
        return _render_docx_fallback(composer_result, output_path)

    structured = composer_result.structured
    sections = structured.sections
    document = Document()

    is_academic = composer_result.output_type in (
        OutputType.RESEARCH_PAPER,
        OutputType.LITERATURE_SURVEY,
    )

    figure_map = {f.figure_id: f for f in structured.figures}
    table_counter = 0
    figure_counter = 0

    if is_academic:
        # ===================================================================
        # ACADEMIC LAYOUT (Research Paper & Literature Survey)
        # ===================================================================
        _configure_academic_page_and_styles(document)
        _setup_academic_footer(document)

        start_section_idx = 0
        has_front_matter = False

        # Section 1 (single column): Title + Front Matter + Abstract
        if sections and sections[0].heading.strip().lower() == "front matter":
            has_front_matter = True
            start_section_idx = 1
            front_section = sections[0]
            para_blocks = [b for b in front_section.blocks if b.kind == "paragraph" and b.text and b.text.strip()]

            # Determine title: if first block matches composer_result.title, use it; else composer_result.title
            if para_blocks and para_blocks[0].text.strip().lower() == composer_result.title.strip().lower():
                title_text = composer_result.title
                front_lines = para_blocks[1:]
            else:
                title_text = composer_result.title
                front_lines = para_blocks

            # Title: centered, bold, 15pt
            tp = document.add_paragraph(style="Title")
            tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.first_line_indent = Pt(0)
            tp.paragraph_format.left_indent = Pt(0)
            tp.paragraph_format.right_indent = Pt(0)
            tp.paragraph_format.keep_with_next = True
            tp.paragraph_format.space_before = Pt(0)
            tp.paragraph_format.space_after = Pt(8)
            trun = tp.add_run(title_text)
            trun.font.name = theme.FONT_ACADEMIC
            trun.font.size = Pt(theme.FONT_SIZE_ACADEMIC_TITLE)
            trun.font.bold = True

            # Front Matter lines:
            # - Line 0: Authors line (bold, 12pt, centered)
            # - Line 1: Affiliation line(s) (11pt, centered)
            # - Line 2+: Optional email/date line (centered)
            for idx, p_block in enumerate(front_lines):
                line_text = p_block.text.strip()
                lp = document.add_paragraph()
                lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                lp.paragraph_format.keep_with_next = True
                lp.paragraph_format.space_before = Pt(4 if idx == 0 else 0)
                lp.paragraph_format.space_after = Pt(2 if idx < len(front_lines) - 1 else 8)
                lrun = lp.add_run(line_text)
                lrun.font.name = theme.FONT_ACADEMIC
                if idx == 0:
                    lrun.font.size = Pt(theme.FONT_SIZE_ACADEMIC_AUTHORS)
                    lrun.font.bold = True
                elif idx == 1:
                    lrun.font.size = Pt(theme.FONT_SIZE_ACADEMIC_AFFILIATION)
                else:
                    lrun.font.size = Pt(theme.FONT_SIZE_ACADEMIC_AFFILIATION)

            # Any non-paragraph front matter blocks
            for b in front_section.blocks:
                if b.kind != "paragraph":
                    if b.kind == "bullets":
                        for item in b.items:
                            document.add_paragraph(item, style="List Bullet")
                    elif b.kind == "table":
                        table_counter += 1
                        cap = f"Table {table_counter}: {b.caption}" if b.caption else f"Table {table_counter}"
                        _render_academic_table(document, b.table_header, b.table_rows, cap, width_cm=theme.DOCX_ACADEMIC_PRINTABLE_WIDTH_CM)
                    elif b.kind == "callout":
                        _render_academic_callout(document, b)
                    elif b.kind == "key_numbers":
                        _render_academic_key_numbers(document, b)
                    elif b.kind == "figure":
                        figure_counter = _render_figure_block(
                            document=document,
                            block=b,
                            figure_map=figure_map,
                            figure_counter=figure_counter,
                            is_academic=True,
                            width_cm=theme.DOCX_ACADEMIC_PRINTABLE_WIDTH_CM,
                        )
        else:
            # Standalone document title
            tp = document.add_paragraph(style="Title")
            tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.first_line_indent = Pt(0)
            tp.paragraph_format.left_indent = Pt(0)
            tp.paragraph_format.right_indent = Pt(0)
            tp.paragraph_format.keep_with_next = True
            tp.paragraph_format.space_before = Pt(0)
            tp.paragraph_format.space_after = Pt(8)
            trun = tp.add_run(composer_result.title)
            trun.font.name = theme.FONT_ACADEMIC
            trun.font.size = Pt(theme.FONT_SIZE_ACADEMIC_TITLE)
            trun.font.bold = True

        # Abstract in Section 1 (single column)
        # Check if next section is Abstract
        abstract_section: Optional[DocSection] = None
        remaining_sections: list[DocSection] = []

        for sec in sections[start_section_idx:]:
            if sec.heading.strip().lower() == "abstract" and abstract_section is None:
                abstract_section = sec
            else:
                remaining_sections.append(sec)

        if abstract_section is not None:
            # Centered bold heading "Abstract" (12pt)
            ab_h = document.add_paragraph(style="Heading 1")
            ab_h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ab_h.paragraph_format.keep_with_next = True
            ab_h.paragraph_format.space_before = Pt(12)
            ab_h.paragraph_format.space_after = Pt(6)
            ab_run = ab_h.add_run("Abstract")
            ab_run.font.name = theme.FONT_ACADEMIC
            ab_run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_ABSTRACT_HEADING)
            ab_run.font.bold = True

            # Abstract text: 10pt justified in narrow centered block (~7.7 cm wide)
            # Total width = 16.0 cm, narrow centered block = 7.7 cm -> indent (16.0 - 7.7) / 2 = 4.15 cm
            side_indent_cm = (theme.DOCX_ACADEMIC_PRINTABLE_WIDTH_CM - theme.DOCX_ACADEMIC_ABSTRACT_WIDTH_CM) / 2.0
            for b in abstract_section.blocks:
                if b.kind == "paragraph" and b.text:
                    p = document.add_paragraph(b.text, style="Normal")
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p.paragraph_format.line_spacing = 1.0
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(4)
                    p.paragraph_format.left_indent = Cm(side_indent_cm)
                    p.paragraph_format.right_indent = Cm(side_indent_cm)
                    p.paragraph_format.first_line_indent = Pt(0)
                    for run in p.runs:
                        run.font.name = theme.FONT_ACADEMIC
                        run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_ABSTRACT_BODY)
                elif b.kind == "bullets":
                    for item in b.items:
                        p = document.add_paragraph(item, style="List Bullet")
                        p.paragraph_format.line_spacing = 1.0
                        p.paragraph_format.space_after = Pt(2)
                        p.paragraph_format.left_indent = Cm(side_indent_cm + 0.3)
                        p.paragraph_format.right_indent = Cm(side_indent_cm)
                        for run in p.runs:
                            run.font.name = theme.FONT_ACADEMIC
                            run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_ABSTRACT_BODY)

        # Open TWO-COLUMN body section via CONTINUOUS break
        body_section = document.add_section(WD_SECTION_START.CONTINUOUS)
        _set_section_columns(body_section, num_cols=2, space_cm=theme.DOCX_ACADEMIC_COL_SPACING_CM)
        body_section.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
        body_section.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
        body_section.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
        body_section.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)

        h1_counter = 0
        h2_counter = 0
        h3_counter = 0
        is_first_para_after_heading = False

        for section in remaining_sections:
            heading_raw = section.heading.strip()

            # Detect heading level
            if heading_raw.startswith("### "):
                level = 3
                heading_clean = heading_raw[4:].strip()
            elif heading_raw.startswith("## "):
                level = 2
                heading_clean = heading_raw[3:].strip()
            elif heading_raw.startswith("# "):
                level = 1
                heading_clean = heading_raw[2:].strip()
            else:
                level = 1
                heading_clean = heading_raw

            heading_lower = heading_clean.lower()
            is_unnumbered = heading_lower in UNNUMBERED_HEADINGS

            if is_unnumbered:
                display_heading = heading_clean
            else:
                if level == 1:
                    h1_counter += 1
                    h2_counter = 0
                    h3_counter = 0
                    display_heading = f"{h1_counter} {heading_clean}"
                elif level == 2:
                    h2_counter += 1
                    h3_counter = 0
                    prefix = f"{h1_counter}.{h2_counter}" if h1_counter > 0 else f"{h2_counter}"
                    display_heading = f"{prefix} {heading_clean}"
                else:
                    h3_counter += 1
                    prefix = f"{h1_counter}.{h2_counter}.{h3_counter}" if h2_counter > 0 else f"{h3_counter}"
                    display_heading = f"{prefix} {heading_clean}"

            # Check if this section immediately starts with a wide table or wide figure
            first_b = section.blocks[0] if section.blocks else None
            is_first_wide_table = False
            if first_b and first_b.kind == "table":
                n_cols = len(first_b.table_header) if first_b.table_header else (len(first_b.table_rows[0]) if first_b.table_rows else 1)
                long_t = any(len(str(c)) > 35 for row in first_b.table_rows for c in row) or any(len(str(h)) > 35 for h in first_b.table_header)
                is_first_wide_table = (n_cols >= 4) or long_t

            if is_first_wide_table:
                # Open wide 1-column section BEFORE the heading so heading, caption, and table stay together
                sec_wide = document.add_section(WD_SECTION_START.CONTINUOUS)
                _set_section_columns(sec_wide, num_cols=1)
                sec_wide.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                sec_wide.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                sec_wide.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                sec_wide.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)

            h_para = document.add_heading(display_heading, level=level)
            h_para.paragraph_format.keep_with_next = True
            is_first_para_after_heading = True

            # References section special formatting
            if heading_lower == "references":
                for b in section.blocks:
                    if b.kind == "bullets":
                        for item in b.items:
                            p = document.add_paragraph(item, style="References")
                            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                            p.paragraph_format.left_indent = Cm(theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
                            p.paragraph_format.first_line_indent = Cm(-theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
                            p.paragraph_format.space_before = Pt(0)
                            p.paragraph_format.space_after = Pt(2)
                            for run in p.runs:
                                run.font.name = theme.FONT_ACADEMIC
                                run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_REFERENCES)
                    elif b.kind == "paragraph":
                        raw_text = b.text or ""
                        entries = [line.strip() for line in raw_text.split("\n") if line.strip()] or [raw_text]
                        for entry in entries:
                            if entry:
                                p = document.add_paragraph(entry, style="References")
                                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                                p.paragraph_format.left_indent = Cm(theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
                                p.paragraph_format.first_line_indent = Cm(-theme.DOCX_ACADEMIC_REF_HANGING_INDENT_CM)
                                p.paragraph_format.space_before = Pt(0)
                                p.paragraph_format.space_after = Pt(2)
                                for run in p.runs:
                                    run.font.name = theme.FONT_ACADEMIC
                                    run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_REFERENCES)
                continue

            # Standard body block rendering
            for block in section.blocks:
                if block.kind == "paragraph":
                    if block.text:
                        p = document.add_paragraph(block.text, style="Normal")
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        p.paragraph_format.line_spacing = 1.0
                        p.paragraph_format.space_before = Pt(0)
                        p.paragraph_format.space_after = Pt(0)
                        for run in p.runs:
                            run.font.name = theme.FONT_ACADEMIC
                            run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_BODY)

                        if is_first_para_after_heading:
                            p.paragraph_format.first_line_indent = Pt(0)
                            is_first_para_after_heading = False
                        else:
                            p.paragraph_format.first_line_indent = Cm(theme.DOCX_ACADEMIC_FIRST_LINE_INDENT_CM)

                elif block.kind == "bullets":
                    for item in block.items:
                        p = document.add_paragraph(item, style="List Bullet")
                        p.paragraph_format.line_spacing = 1.0
                        p.paragraph_format.space_before = Pt(0)
                        p.paragraph_format.space_after = Pt(2)
                        for run in p.runs:
                            run.font.name = theme.FONT_ACADEMIC
                            run.font.size = Pt(theme.FONT_SIZE_ACADEMIC_BODY)
                    is_first_para_after_heading = False

                elif block.kind == "table":
                    table_counter += 1
                    cap = f"Table {table_counter}: {block.caption}" if block.caption else f"Table {table_counter}"

                    num_tbl_cols = len(block.table_header) if block.table_header else (len(block.table_rows[0]) if block.table_rows else 1)
                    has_long_text = any(len(str(c)) > 35 for row in block.table_rows for c in row) or any(len(str(h)) > 35 for h in block.table_header)
                    is_wide_table = (num_tbl_cols >= 4) or has_long_text

                    if is_wide_table:
                        if not is_first_wide_table:
                            sec_wide = document.add_section(WD_SECTION_START.CONTINUOUS)
                            _set_section_columns(sec_wide, num_cols=1)
                            sec_wide.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)

                        _render_academic_table(
                            document=document,
                            table_header=block.table_header,
                            table_rows=block.table_rows,
                            caption_text=cap,
                            width_cm=theme.DOCX_ACADEMIC_PRINTABLE_WIDTH_CM,
                        )

                        sec_reopen = document.add_section(WD_SECTION_START.CONTINUOUS)
                        _set_section_columns(sec_reopen, num_cols=2, space_cm=theme.DOCX_ACADEMIC_COL_SPACING_CM)
                        sec_reopen.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                        sec_reopen.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                        sec_reopen.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                        sec_reopen.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                    else:
                        _render_academic_table(
                            document=document,
                            table_header=block.table_header,
                            table_rows=block.table_rows,
                            caption_text=cap,
                            width_cm=theme.DOCX_ACADEMIC_COL_WIDTH_CM,
                        )
                    is_first_para_after_heading = False

                elif block.kind == "figure":
                    fig = figure_map.get(block.figure_id) if block.figure_id else None
                    if fig is None:
                        figure_counter = _render_figure_block(
                            document=document,
                            block=block,
                            figure_map=figure_map,
                            figure_counter=figure_counter,
                            is_academic=True,
                            width_cm=theme.DOCX_ACADEMIC_COL_WIDTH_CM,
                        )
                    else:
                        is_wide_fig = (fig.kind == "diagram") or (fig.labels and len(fig.labels) > 6)
                        if is_wide_fig:
                            sec_wide = document.add_section(WD_SECTION_START.CONTINUOUS)
                            _set_section_columns(sec_wide, num_cols=1)
                            sec_wide.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_wide.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)

                            figure_counter = _render_figure_block(
                                document=document,
                                block=block,
                                figure_map=figure_map,
                                figure_counter=figure_counter,
                                is_academic=True,
                                width_cm=theme.DOCX_ACADEMIC_PRINTABLE_WIDTH_CM,
                            )

                            sec_reopen = document.add_section(WD_SECTION_START.CONTINUOUS)
                            _set_section_columns(sec_reopen, num_cols=2, space_cm=theme.DOCX_ACADEMIC_COL_SPACING_CM)
                            sec_reopen.top_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_reopen.bottom_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_reopen.left_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                            sec_reopen.right_margin = Cm(theme.DOCX_ACADEMIC_PAGE_MARGIN_CM)
                        else:
                            figure_counter = _render_figure_block(
                                document=document,
                                block=block,
                                figure_map=figure_map,
                                figure_counter=figure_counter,
                                is_academic=True,
                                width_cm=theme.DOCX_ACADEMIC_COL_WIDTH_CM,
                            )
                    is_first_para_after_heading = False

                elif block.kind == "callout":
                    _render_academic_callout(document, block)
                    is_first_para_after_heading = False

                elif block.kind == "key_numbers":
                    _render_academic_key_numbers(document, block)
                    is_first_para_after_heading = False

    else:
        # ===================================================================
        # MODERN LAYOUT (Executive Summary)
        # ===================================================================
        _configure_modern_page_and_styles(document)
        _setup_modern_header_and_footer(document, composer_result.title)

        start_section_idx = 0
        has_front_matter = False

        if sections and sections[0].heading.strip().lower() == "front matter":
            has_front_matter = True
            start_section_idx = 1
            front_section = sections[0]
            para_blocks = [b for b in front_section.blocks if b.kind == "paragraph" and b.text and b.text.strip()]

            # Determine title and subtitle/meta lines
            if para_blocks and para_blocks[0].text.strip().lower() == composer_result.title.strip().lower():
                title_text = composer_result.title
                front_lines = para_blocks[1:]
            else:
                title_text = composer_result.title
                front_lines = para_blocks

            # Title (primary color, 22pt bold)
            tp = document.add_paragraph(title_text, style="Title")
            tp.paragraph_format.keep_with_next = True
            tp.paragraph_format.space_before = Pt(0)
            tp.paragraph_format.space_after = Pt(4)
            if tp.runs:
                tp.runs[0].font.size = Pt(22.0)
                tp.runs[0].font.bold = True
                tp.runs[0].font.color.rgb = _hex_to_rgb(theme.PRIMARY)

            # Front matter lines in muted color
            for p_block in front_lines:
                lp = document.add_paragraph()
                lp.paragraph_format.keep_with_next = True
                lp.paragraph_format.space_before = Pt(0)
                lp.paragraph_format.space_after = Pt(3)
                lrun = lp.add_run(p_block.text.strip())
                lrun.font.name = theme.FONT_WORD
                lrun.font.size = Pt(10.0)
                lrun.font.color.rgb = _hex_to_rgb(theme.MUTED)

            # Thin accent rule
            _add_accent_rule(document, space_after_pt=12)

            # Any non-paragraph front matter blocks
            for b in front_section.blocks:
                if b.kind != "paragraph":
                    if b.kind == "bullets":
                        for item in b.items:
                            document.add_paragraph(item, style="List Bullet")
                    elif b.kind == "table":
                        table_counter += 1
                        cap = f"Table {table_counter}: {b.caption}" if b.caption else f"Table {table_counter}"
                        _render_modern_table(document, b.table_header, b.table_rows, cap)
                    elif b.kind == "callout":
                        _render_callout_block(document, b)
                    elif b.kind == "key_numbers":
                        _render_key_numbers_block(document, b)
                    elif b.kind == "figure":
                        figure_counter = _render_figure_block(document, b, figure_map, figure_counter, is_academic=False)
        else:
            tp = document.add_paragraph(composer_result.title, style="Title")
            tp.paragraph_format.keep_with_next = True
            if tp.runs:
                tp.runs[0].font.size = Pt(22.0)
                tp.runs[0].font.bold = True
                tp.runs[0].font.color.rgb = _hex_to_rgb(theme.PRIMARY)
            _add_accent_rule(document, space_after_pt=12)

        # Body sections for Executive Summary (Unnumbered headings in primary color)
        for section in sections[start_section_idx:]:
            heading_raw = section.heading.strip()
            if heading_raw.startswith("### "):
                level = 3
                heading_clean = heading_raw[4:].strip()
            elif heading_raw.startswith("## "):
                level = 2
                heading_clean = heading_raw[3:].strip()
            elif heading_raw.startswith("# "):
                level = 1
                heading_clean = heading_raw[2:].strip()
            else:
                level = 1
                heading_clean = heading_raw

            h_para = document.add_heading(heading_clean, level=level)
            h_para.paragraph_format.keep_with_next = True

            for block in section.blocks:
                if block.kind == "paragraph":
                    if block.text:
                        document.add_paragraph(block.text, style="Normal")
                elif block.kind == "bullets":
                    for item in block.items:
                        document.add_paragraph(item, style="List Bullet")
                elif block.kind == "table":
                    table_counter += 1
                    cap = f"Table {table_counter}: {block.caption}" if block.caption else f"Table {table_counter}"
                    _render_modern_table(
                        document=document,
                        table_header=block.table_header,
                        table_rows=block.table_rows,
                        caption_text=cap,
                    )
                elif block.kind == "callout":
                    _render_callout_block(document, block)
                elif block.kind == "key_numbers":
                    _render_key_numbers_block(document, block)
                elif block.kind == "figure":
                    figure_counter = _render_figure_block(
                        document=document,
                        block=block,
                        figure_map=figure_map,
                        figure_counter=figure_counter,
                        is_academic=False,
                    )

    document.save(output_path)
    return output_path