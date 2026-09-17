from pathlib import Path

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)

from backend.schemas.schemas import ComposerResult


def render_pdf(
    composer_result: ComposerResult,
    output_path: str | Path,
) -> Path:
    """
    Render a ComposerResult into a PDF document.

    The renderer only formats the content supplied by the Composer.
    It does not generate or modify research content.
    """
    output_path = Path(output_path)

    if output_path.suffix.lower() != ".pdf":
        raise ValueError("Output path must have a .pdf extension.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(output_path),
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    heading_style = styles["Heading1"]
    body_style = styles["BodyText"]

    story = []

    # Add document title
    story.append(
        Paragraph(composer_result.title, title_style)
    )
    story.append(Spacer(1, 0.2 * inch))

    # Add sections in the same order supplied by Composer
    for section_name, section_content in composer_result.sections.items():
        story.append(
            Paragraph(section_name, heading_style)
        )

        if section_content:
            safe_content = (
                section_content
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
            )

            story.append(
                Paragraph(safe_content, body_style)
            )

        story.append(Spacer(1, 0.1 * inch))

    # Build the PDF from the flowable elements
    document.build(story)

    return output_path