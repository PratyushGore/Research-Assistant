from backend.schemas.schemas import (
    CitationResult,
    FindingsPacket,
    GuidedInputBundle,
    OutputType,
    ProjectPresentationInfo,
    AcademicContentInfo,
)


def _format_findings(findings: FindingsPacket) -> str:
    """Create a deterministic text block from research findings."""
    if not findings.summaries:
        return "No research findings were provided."

    parts = []

    for summary in findings.summaries:
        parts.append(f"Paper: {summary.paper_id}")
        parts.append(f"Summary: {summary.summary}")

        if summary.key_findings:
            parts.append("Key Findings:")
            for finding in summary.key_findings:
                parts.append(f"- {finding}")

    return "\n".join(parts)


def _format_references(citation_result: CitationResult) -> str:
    """Create a references section from the citation agent output."""
    if not citation_result.bibliography:
        return "No references available."

    return "\n".join(
        f"{index}. {reference}"
        for index, reference in enumerate(citation_result.bibliography, start=1)
    )


def _cover_text(guided_input: GuidedInputBundle) -> str:
    """Create a cover block from guided input."""
    cover = guided_input.cover_info

    lines = [f"Title: {cover.title}"]

    if cover.subtitle:
        lines.append(f"Subtitle: {cover.subtitle}")

    if cover.authors:
        lines.append(f"Authors: {', '.join(cover.authors)}")

    if cover.institution:
        lines.append(f"Institution: {cover.institution}")

    if cover.date:
        lines.append(f"Date: {cover.date}")

    return "\n".join(lines)


def generate_literature_survey(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> dict[str, str]:
    """Generate deterministic Literature Survey sections."""
    return {
        "Abstract": (
            f"This literature survey examines research related to "
            f"{findings.topic}."
        ),
        "Introduction": (
            f"The survey focuses on existing research concerning "
            f"{findings.topic}."
        ),
        "Thematic Review": _format_findings(findings),
        "Synthesis": (
            "The reviewed studies provide the research findings presented "
            "above and can be compared to identify common themes and gaps."
        ),
        "Conclusion": (
            f"The reviewed literature provides a foundation for further "
            f"work related to {findings.topic}."
        ),
        "References": _format_references(citation_result),
    }


def generate_executive_summary(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> dict[str, str]:
    """Generate deterministic Executive Summary sections."""
    return {
        "Cover": _cover_text(guided_input),
        "Overview": (
            f"This executive summary presents the main research findings "
            f"related to {findings.topic}."
        ),
        "Key Findings": _format_findings(findings),
        "Implications": (
            "The findings can be used to understand the current research "
            "landscape and identify areas for further investigation."
        ),
    }


def generate_ppt(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> dict[str, str]:
    """Generate deterministic PPT content."""
    presentation = guided_input.project_presentation_info

    if presentation is None:
        raise ValueError(
            "Project Presentation Info is required for PPT generation."
        )

    return {
        "Title": _cover_text(guided_input),
        "Problem": presentation.problem_statement,
        "Literature Findings": _format_findings(findings),
        "Own Approach/Architecture": presentation.own_architecture_summary,
        "Own Results": presentation.own_results_summary,
        "Comparison": (
            "Compare the project's approach and results with the "
            "verified literature findings."
        ),
        "Conclusion": (
            f"The project addresses the stated problem related to "
            f"{findings.topic}."
        ),
    }


def generate_research_paper(
    guided_input: GuidedInputBundle,
    findings: FindingsPacket,
    citation_result: CitationResult,
) -> dict[str, str]:
    """Generate Research Paper sections without fabricating academic content."""
    academic = guided_input.academic_content_info

    if academic is None:
        raise ValueError(
            "Academic Content Info is required for Research Paper generation."
        )

    return {
        "Abstract": (
            f"This research paper presents work related to "
            f"{findings.topic}. The paper is based on the provided "
            f"academic content and verified research findings."
        ),
        "Introduction": (
            f"The research addresses the topic of {findings.topic}."
        ),
        "Literature Review": _format_findings(findings),
        "Methodology": (
            f"Methodology: {academic.methodology}\n"
            f"Dataset/Sample: {academic.dataset_or_sample}\n"
            f"Tools Used: {', '.join(academic.tools_used)}\n"
            f"What Was Measured: {academic.what_was_measured}"
        ),
        "Results/Discussion": (
            f"Key Results: {academic.key_results}\n"
            f"Limitations: "
            f"{academic.limitations or 'No limitations provided.'}"
        ),
        "Conclusion": (
            f"The provided academic content and research findings "
            f"support further work related to {findings.topic}."
        ),
        "References": _format_references(citation_result),
    }