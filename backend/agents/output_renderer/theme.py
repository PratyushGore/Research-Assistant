"""
Design theme constants for document and presentation output renderers.
Plain constants only: palette, fonts, size scale, spacing, and dimensions.
"""

from typing import Final, Mapping, Tuple

# ---------------------------------------------------------------------------
# Color Palette (Hex strings)
# ---------------------------------------------------------------------------
PRIMARY: Final[str] = "#1E3A8A"
ACCENT: Final[str] = "#2563EB"
TEXT: Final[str] = "#1F2937"
MUTED: Final[str] = "#6B7280"
BACKGROUND: Final[str] = "#FFFFFF"
TABLE_HEADER_FILL: Final[str] = "#F3F4F6"
TABLE_STRIPE_FILL: Final[str] = "#F9FAFB"
CALLOUT_FILL: Final[str] = "#EFF6FF"

COLOR_PRIMARY: Final[str] = PRIMARY
COLOR_ACCENT: Final[str] = ACCENT
COLOR_TEXT: Final[str] = TEXT
COLOR_MUTED: Final[str] = MUTED
COLOR_BACKGROUND: Final[str] = BACKGROUND
COLOR_TABLE_HEADER_FILL: Final[str] = TABLE_HEADER_FILL
COLOR_TABLE_STRIPE_FILL: Final[str] = TABLE_STRIPE_FILL
COLOR_CALLOUT_FILL: Final[str] = CALLOUT_FILL

PALETTE: Final[Mapping[str, str]] = {
    "primary": PRIMARY,
    "accent": ACCENT,
    "text": TEXT,
    "muted": MUTED,
    "background": BACKGROUND,
    "table_header_fill": TABLE_HEADER_FILL,
    "table_stripe_fill": TABLE_STRIPE_FILL,
    "callout_fill": CALLOUT_FILL,
}

# ---------------------------------------------------------------------------
# Font Names
# ---------------------------------------------------------------------------
FONT_WORD: Final[str] = "Calibri"
FONT_WORD_FALLBACK: Final[str] = "Arial"
FONT_PPT: Final[str] = "Calibri"
FONT_PPT_FALLBACK: Final[str] = "Arial"
FONT_PDF: Final[str] = "Helvetica"

FONTS: Final[Mapping[str, str]] = {
    "word": FONT_WORD,
    "word_fallback": FONT_WORD_FALLBACK,
    "ppt": FONT_PPT,
    "ppt_fallback": FONT_PPT_FALLBACK,
    "pdf": FONT_PDF,
}

# ---------------------------------------------------------------------------
# Size Scale (in points / pt)
# ---------------------------------------------------------------------------
FONT_SIZE_TITLE: Final[float] = 24.0
FONT_SIZE_H1: Final[float] = 18.0
FONT_SIZE_H2: Final[float] = 14.0
FONT_SIZE_BODY: Final[float] = 11.0
FONT_SIZE_CAPTION: Final[float] = 9.0

SIZE_SCALE: Final[Mapping[str, float]] = {
    "title": FONT_SIZE_TITLE,
    "h1": FONT_SIZE_H1,
    "h2": FONT_SIZE_H2,
    "body": FONT_SIZE_BODY,
    "caption": FONT_SIZE_CAPTION,
}

FONT_SIZES: Final[Mapping[str, float]] = SIZE_SCALE

# ---------------------------------------------------------------------------
# Spacing Values (in points / pt)
# ---------------------------------------------------------------------------
SPACING_XS: Final[float] = 4.0
SPACING_SM: Final[float] = 8.0
SPACING_MD: Final[float] = 12.0
SPACING_LG: Final[float] = 16.0
SPACING_XL: Final[float] = 24.0
SPACING_PARAGRAPH_AFTER: Final[float] = 6.0
SPACING_SECTION_AFTER: Final[float] = 12.0
SPACING_LINE_HEIGHT: Final[float] = 1.15

SPACING: Final[Mapping[str, float]] = {
    "xs": SPACING_XS,
    "sm": SPACING_SM,
    "md": SPACING_MD,
    "lg": SPACING_LG,
    "xl": SPACING_XL,
    "paragraph_after": SPACING_PARAGRAPH_AFTER,
    "section_after": SPACING_SECTION_AFTER,
    "line_height": SPACING_LINE_HEIGHT,
}

# ---------------------------------------------------------------------------
# Slide Size (16:9 widescreen in inches: 13.333 x 7.5)
# ---------------------------------------------------------------------------
SLIDE_WIDTH_INCHES: Final[float] = 13.333
SLIDE_HEIGHT_INCHES: Final[float] = 7.5
SLIDE_WIDTH: Final[float] = 13.333
SLIDE_HEIGHT: Final[float] = 7.5
SLIDE_SIZE_16_9: Final[Tuple[float, float]] = (13.333, 7.5)
SLIDE_DIMENSIONS_16_9: Final[Tuple[float, float]] = (13.333, 7.5)

# ---------------------------------------------------------------------------
# Presentation Renderer Additive Styling Constants
# ---------------------------------------------------------------------------
DIAGRAM_NODE_FILL: Final[str] = CALLOUT_FILL
DIAGRAM_NODE_BORDER: Final[str] = ACCENT
DIAGRAM_NODE_TEXT: Final[str] = PRIMARY
DIAGRAM_CONNECTOR_COLOR: Final[str] = ACCENT

FOOTER_FONT_SIZE: Final[float] = 12.0
CHART_AXIS_FONT_SIZE: Final[float] = 12.0
TABLE_HEADER_FONT_SIZE: Final[float] = 16.0
TABLE_BODY_FONT_SIZE: Final[float] = 14.0
TABLE_BODY_MIN_FONT_SIZE: Final[float] = 11.0
BULLET_MIN_FONT_SIZE: Final[float] = 16.0

# ---------------------------------------------------------------------------
# Document (DOCX) Renderer Additive Styling Constants
# ---------------------------------------------------------------------------
DOCX_PAGE_MARGIN_CM: Final[float] = 2.54
DOCX_TABLE_BORDER_COLOR: Final[str] = "#E5E7EB"
DOCX_TABLE_BORDER_HEADER_BOTTOM: Final[str] = "#D1D5DB"
DOCX_CALLOUT_BORDER_COLOR: Final[str] = ACCENT
DOCX_CALLOUT_BORDER_SIZE: Final[int] = 24  # 3pt (in eighths of a pt)
FONT_SIZE_SUBTITLE: Final[float] = 13.0
FONT_SIZE_REFERENCES: Final[float] = 10.0
FONT_SIZE_KEY_NUMBER: Final[float] = 24.0
FONT_SIZE_FOOTER: Final[float] = 9.0
FONT_SIZE_HEADER: Final[float] = 9.0

# Academic (ACL-Style) Additive Styling Constants
FONT_ACADEMIC: Final[str] = "Times New Roman"
FONT_ACADEMIC_FALLBACK: Final[str] = "Times"
FONT_SIZE_ACADEMIC_TITLE: Final[float] = 15.0
FONT_SIZE_ACADEMIC_AUTHORS: Final[float] = 12.0
FONT_SIZE_ACADEMIC_AFFILIATION: Final[float] = 11.0
FONT_SIZE_ACADEMIC_ABSTRACT_HEADING: Final[float] = 12.0
FONT_SIZE_ACADEMIC_ABSTRACT_BODY: Final[float] = 10.0
FONT_SIZE_ACADEMIC_H1: Final[float] = 12.0
FONT_SIZE_ACADEMIC_H2: Final[float] = 11.0
FONT_SIZE_ACADEMIC_H3: Final[float] = 11.0
FONT_SIZE_ACADEMIC_BODY: Final[float] = 11.0
FONT_SIZE_ACADEMIC_CAPTION: Final[float] = 10.0
FONT_SIZE_ACADEMIC_TABLE: Final[float] = 10.0
FONT_SIZE_ACADEMIC_REFERENCES: Final[float] = 10.0
FONT_SIZE_ACADEMIC_FOOTER: Final[float] = 10.0

DOCX_ACADEMIC_PAGE_MARGIN_CM: Final[float] = 2.5
DOCX_ACADEMIC_COL_SPACING_CM: Final[float] = 0.6
DOCX_ACADEMIC_COL_WIDTH_CM: Final[float] = 7.7
DOCX_ACADEMIC_PRINTABLE_WIDTH_CM: Final[float] = 16.0
DOCX_ACADEMIC_ABSTRACT_WIDTH_CM: Final[float] = 7.7
DOCX_ACADEMIC_FIRST_LINE_INDENT_CM: Final[float] = 0.4
DOCX_ACADEMIC_REF_HANGING_INDENT_CM: Final[float] = 0.5


