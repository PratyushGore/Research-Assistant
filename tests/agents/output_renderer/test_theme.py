import re
import pytest

from backend.agents.output_renderer import theme


HEX_COLOR_REGEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class TestThemeConstants:
    def test_palette_constants_exist_and_valid_hex(self):
        expected_keys = [
            "primary",
            "accent",
            "text",
            "muted",
            "background",
            "table_header_fill",
            "table_stripe_fill",
            "callout_fill",
        ]
        assert hasattr(theme, "PALETTE")
        for key in expected_keys:
            assert key in theme.PALETTE, f"Missing palette key: {key}"
            hex_val = theme.PALETTE[key]
            assert isinstance(hex_val, str)
            assert HEX_COLOR_REGEX.match(hex_val), f"Invalid hex color for '{key}': {hex_val}"

        # Test individual constants
        assert HEX_COLOR_REGEX.match(theme.PRIMARY)
        assert HEX_COLOR_REGEX.match(theme.ACCENT)
        assert HEX_COLOR_REGEX.match(theme.TEXT)
        assert HEX_COLOR_REGEX.match(theme.MUTED)
        assert HEX_COLOR_REGEX.match(theme.BACKGROUND)
        assert HEX_COLOR_REGEX.match(theme.TABLE_HEADER_FILL)
        assert HEX_COLOR_REGEX.match(theme.TABLE_STRIPE_FILL)
        assert HEX_COLOR_REGEX.match(theme.CALLOUT_FILL)

    def test_fonts_exist(self):
        assert theme.FONT_WORD in ("Calibri", "Arial")
        assert theme.FONT_PPT in ("Calibri", "Arial")
        assert theme.FONT_PDF == "Helvetica"
        assert "word" in theme.FONTS
        assert "ppt" in theme.FONTS
        assert "pdf" in theme.FONTS

    def test_size_scale_in_pt(self):
        expected_sizes = ["title", "h1", "h2", "body", "caption"]
        assert hasattr(theme, "SIZE_SCALE")
        for key in expected_sizes:
            assert key in theme.SIZE_SCALE
            size = theme.SIZE_SCALE[key]
            assert isinstance(size, (int, float))
            assert size > 0

        assert theme.FONT_SIZE_TITLE > theme.FONT_SIZE_H1 > theme.FONT_SIZE_H2 > theme.FONT_SIZE_BODY > theme.FONT_SIZE_CAPTION

    def test_spacing_values(self):
        assert hasattr(theme, "SPACING")
        for key in ["xs", "sm", "md", "lg", "xl"]:
            assert key in theme.SPACING
            assert theme.SPACING[key] > 0

    def test_slide_dimensions_16_9(self):
        assert theme.SLIDE_WIDTH_INCHES == pytest.approx(13.333, abs=0.001)
        assert theme.SLIDE_HEIGHT_INCHES == pytest.approx(7.5, abs=0.001)
        assert theme.SLIDE_SIZE_16_9 == (pytest.approx(13.333, abs=0.001), pytest.approx(7.5, abs=0.001))
