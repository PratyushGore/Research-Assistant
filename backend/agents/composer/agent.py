from __future__ import annotations

import logging
from typing import Any, Optional

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

logger = logging.getLogger("research_assistant.composer")


class ComposerAgent:
    """Creates structured research outputs from verified inputs."""

    SUPPORTED_OUTPUTS = {
        OutputType.LITERATURE_SURVEY,
        OutputType.EXECUTIVE_SUMMARY,
        OutputType.PPT,
        OutputType.RESEARCH_PAPER,
    }

    def __init__(self, llm: Optional[Any] = None) -> None:
        self.llm = llm

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

        result = ComposerResult(
            output_type=output_type,
            title=guided_input.cover_info.title,
            content=content,
            sections=sections,
            citations_used=citations_used,
        )

        # For PPT only: attach structured 16:9 presentation specifications
        if output_type == OutputType.PPT:
            try:
                from .ppt_content import build_ppt_structured

                result.structured = build_ppt_structured(
                    guided_input=guided_input,
                    findings=findings,
                    citation_result=citation_result,
                    llm=self.llm,
                )
            except Exception as exc:
                logger.warning("Failed to build structured PPT content: %s", exc, exc_info=True)
                result.structured = None

        elif output_type in (
            OutputType.RESEARCH_PAPER,
            OutputType.LITERATURE_SURVEY,
            OutputType.EXECUTIVE_SUMMARY,
        ):
            try:
                from .doc_content import build_doc_structured

                result.structured = build_doc_structured(
                    output_type=output_type,
                    guided_input=guided_input,
                    findings=findings,
                    citation_result=citation_result,
                    llm=self.llm,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to build structured doc content for %s: %s",
                    output_type,
                    exc,
                    exc_info=True,
                )
                result.structured = None

        return result


composer_agent = ComposerAgent()