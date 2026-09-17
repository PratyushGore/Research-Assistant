from pathlib import Path

from backend.schemas.schemas import ComposerResult, OutputType

from .docx_renderer import render_docx
from .pdf_renderer import render_pdf
from .pptx_renderer import render_pptx


SUPPORTED_FORMATS = {
    OutputType.LITERATURE_SURVEY: {"docx", "pdf"},
    OutputType.EXECUTIVE_SUMMARY: {"docx", "pdf"},
    OutputType.PPT: {"pptx"},
    OutputType.RESEARCH_PAPER: {"docx", "pdf"},
}


def render_output(
    composer_result: ComposerResult,
    output_format: str,
    output_path: str | Path,
) -> Path:
    """
    Select and run the appropriate renderer for a ComposerResult.

    The renderer only formats content supplied by the Composer.
    It does not generate or modify research content.
    """
    output_format = output_format.strip().lower()
    output_path = Path(output_path)

    output_type = composer_result.output_type

    if output_type not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported output type: {output_type}")

    if output_format not in SUPPORTED_FORMATS[output_type]:
        raise ValueError(
            f"Format '{output_format}' is not supported for "
            f"output type '{output_type.value}'."
        )

    if output_format == "docx":
        return render_docx(composer_result, output_path)

    if output_format == "pdf":
        return render_pdf(composer_result, output_path)

    if output_format == "pptx":
        return render_pptx(composer_result, output_path)

    raise ValueError(f"Unsupported output format: {output_format}")