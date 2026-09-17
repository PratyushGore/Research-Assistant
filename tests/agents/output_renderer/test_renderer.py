from pathlib import Path

import pytest

from backend.agents.output_renderer.renderer import render_output
from backend.schemas.schemas import ComposerResult, OutputType


def sample_composer_result(output_type: OutputType) -> ComposerResult:
    return ComposerResult(
        output_type=output_type,
        title="AI Research Assistant",
        content="Sample content.",
        sections={
            "Introduction": "This is sample introduction content.",
            "Conclusion": "This is sample conclusion content.",
        },
        citations_used=["citation-paper-001"],
    )


def test_render_research_paper_as_docx(tmp_path: Path):
    output_path = tmp_path / "research_paper.docx"

    result = render_output(
        sample_composer_result(OutputType.RESEARCH_PAPER),
        "docx",
        output_path,
    )

    assert result == output_path
    assert output_path.exists()


def test_render_research_paper_as_pdf(tmp_path: Path):
    output_path = tmp_path / "research_paper.pdf"

    result = render_output(
        sample_composer_result(OutputType.RESEARCH_PAPER),
        "pdf",
        output_path,
    )

    assert result == output_path
    assert output_path.exists()


def test_render_ppt_as_pptx(tmp_path: Path):
    output_path = tmp_path / "presentation.pptx"

    result = render_output(
        sample_composer_result(OutputType.PPT),
        "pptx",
        output_path,
    )

    assert result == output_path
    assert output_path.exists()


def test_render_output_accepts_uppercase_format(tmp_path: Path):
    output_path = tmp_path / "research_paper.pdf"

    result = render_output(
        sample_composer_result(OutputType.RESEARCH_PAPER),
        "PDF",
        output_path,
    )

    assert result == output_path
    assert output_path.exists()


def test_render_output_rejects_unsupported_format(tmp_path: Path):
    output_path = tmp_path / "presentation.pdf"

    with pytest.raises(ValueError, match="not supported"):
        render_output(
            sample_composer_result(OutputType.PPT),
            "pdf",
            output_path,
        )


def test_render_output_rejects_unknown_format(tmp_path: Path):
    output_path = tmp_path / "output.txt"

    with pytest.raises(ValueError, match="not supported"):
        render_output(
            sample_composer_result(OutputType.RESEARCH_PAPER),
            "txt",
            output_path,
        )