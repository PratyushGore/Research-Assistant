from backend.schemas.schemas import OutputTemplate, OutputType


OUTPUT_TEMPLATES = {
    OutputType.LITERATURE_SURVEY: OutputTemplate(
        template_id="literature-survey-v1",
        output_type=OutputType.LITERATURE_SURVEY,
        sections=[
            "Abstract",
            "Introduction",
            "Thematic Review",
            "Synthesis",
            "Conclusion",
            "References",
        ],
        guidelines=(
            "Use the provided cover information and verified research findings. "
            "Organize the literature thematically and support claims with citations."
        ),
    ),
    
    OutputType.EXECUTIVE_SUMMARY: OutputTemplate(
        template_id="executive-summary-v1",
        output_type=OutputType.EXECUTIVE_SUMMARY,
        sections=[
            "Cover",
            "Overview",
            "Key Findings",
            "Implications",
        ],
        guidelines=(
            "Keep the output concise and focused. "
            "Target approximately 2–3 pages."
        ),
    ),
    
    OutputType.PPT: OutputTemplate(
        template_id="ppt-v1",
        output_type=OutputType.PPT,
        sections=[
            "Title",
            "Problem",
            "Literature Findings",
            "Own Approach/Architecture",
            "Own Results",
            "Comparison",
            "Conclusion",
        ],
        guidelines=(
            "Use cover and project presentation information. "
            "Clearly distinguish literature findings from the project's own "
            "approach and results."
        ),
    ),
    
    OutputType.RESEARCH_PAPER: OutputTemplate(
        template_id="research-paper-v1",
        output_type=OutputType.RESEARCH_PAPER,
        sections=[
            "Abstract",
            "Introduction",
            "Literature Review",
            "Methodology",
            "Results/Discussion",
            "Conclusion",
            "References",
        ],
        guidelines=(
            "Use cover information and academic content. "
            "Methodology and results must come from the provided academic "
            "content and must not be fabricated."
        ),
    ),
}


def get_template(output_type: OutputType) -> OutputTemplate:
    """Return the template for the requested output type."""
    if output_type not in OUTPUT_TEMPLATES:
        raise ValueError(f"Unsupported output type: {output_type}")

    return OUTPUT_TEMPLATES[output_type]