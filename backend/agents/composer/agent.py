from backend.schemas.schemas import (
    CitationResult,
    ComposerResult,
    FindingsPacket,
    GuidedInputBundle,
    OutputType,
)

from .generator import (
    generate_executive_summary,
    generate_literature_survey,
    generate_ppt,
    generate_research_paper,
)
from .templates import get_template


class ComposerAgent:
    """Creates structured research outputs from verified inputs."""

    SUPPORTED_OUTPUTS = {
        OutputType.LITERATURE_SURVEY,
        OutputType.EXECUTIVE_SUMMARY,
        OutputType.PPT,
        OutputType.RESEARCH_PAPER,
    }

    def compose(
        self,
        output_type: OutputType,
        guided_input: GuidedInputBundle,
        findings: FindingsPacket,
        citation_result: CitationResult,
    ) -> ComposerResult:
        """Generate one requested output."""

        if output_type not in self.SUPPORTED_OUTPUTS:
            raise ValueError(
                f"Unsupported output type: {output_type}"
            )

        template = get_template(output_type)

        if output_type == OutputType.LITERATURE_SURVEY:
            sections = generate_literature_survey(
                guided_input,
                findings,
                citation_result,
            )

        elif output_type == OutputType.EXECUTIVE_SUMMARY:
            sections = generate_executive_summary(
                guided_input,
                findings,
                citation_result,
            )

        elif output_type == OutputType.PPT:
            sections = generate_ppt(
                guided_input,
                findings,
                citation_result,
            )

        elif output_type == OutputType.RESEARCH_PAPER:
            sections = generate_research_paper(
                guided_input,
                findings,
                citation_result,
            )

        else:
            raise ValueError(
                f"Unsupported output type: {output_type}"
            )

        content_parts = []

        for section in template.sections:
            if section in sections:
                content_parts.append(
                    f"## {section}\n{sections[section]}"
                )

        content = "\n\n".join(content_parts)

        citations_used = [
            citation.citation_id
            for citation in citation_result.citations
        ]

        return ComposerResult(
            output_type=output_type,
            title=guided_input.cover_info.title,
            content=content,
            sections=sections,
            citations_used=citations_used,
        )


composer_agent = ComposerAgent()