from pathlib import Path

from pypdf import PdfReader

from backend.agents.output_renderer.pdf_renderer import render_pdf
from backend.schemas.schemas import ComposerResult, OutputType


def sample_composer_result() -> ComposerResult:
    return ComposerResult(
        output_type=OutputType.RESEARCH_PAPER,
        title="AI Research Assistant",
        content="Research paper content.",
        sections={
            "Abstract": "This is the abstract.",
            "Introduction": "This is the introduction.",
            "Methodology": "This is the methodology.",
            "References": "1. Smith, John. (2025). AI Research.",
        },
        citations_used=["citation-paper-001"],
    )


def test_render_pdf_creates_file(tmp_path: Path):
    output_path = tmp_path / "research_paper.pdf"

    result = render_pdf(
        sample_composer_result(),
        output_path,
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.is_file()


def test_render_pdf_contains_title_and_sections(tmp_path: Path):
    output_path = tmp_path / "research_output.pdf"

    render_pdf(
        sample_composer_result(),
        output_path,
    )

    reader = PdfReader(str(output_path))
    text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    assert "AI Research Assistant" in text
    assert "Abstract" in text
    assert "This is the abstract." in text
    assert "Introduction" in text
    assert "This is the introduction." in text
    assert "Methodology" in text
    assert "References" in text


def test_render_pdf_creates_parent_directory(tmp_path: Path):
    output_path = tmp_path / "generated" / "nested" / "output.pdf"

    render_pdf(
        sample_composer_result(),
        output_path,
    )

    assert output_path.exists()


def test_render_pdf_preserves_section_order(tmp_path: Path):
    output_path = tmp_path / "ordered.pdf"

    render_pdf(
        sample_composer_result(),
        output_path,
    )

    reader = PdfReader(str(output_path))
    text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    assert text.index("Abstract") < text.index("Introduction")
    assert text.index("Introduction") < text.index("Methodology")
    assert text.index("Methodology") < text.index("References")


def test_render_pdf_rejects_non_pdf_path(tmp_path: Path):
    output_path = tmp_path / "output.docx"

    try:
        render_pdf(
            sample_composer_result(),
            output_path,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Output path must have a .pdf extension" in str(exc)