from typing import Any

from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    OutputType,
    ProjectPresentationInfo,
)


def validate_topic(topic: Any) -> tuple[bool, str]:
    """Validate the research topic."""
    if not isinstance(topic, str) or not topic.strip():
        return False, "Research topic is required."

    return True, ""


def validate_output_types(
    output_types: Any,
) -> tuple[bool, str]:
    """Validate the selected output types."""
    if not isinstance(output_types, list) or not output_types:
        return False, "At least one output type must be selected."

    for output_type in output_types:
        if not isinstance(output_type, OutputType):
            try:
                OutputType(output_type)
            except (ValueError, TypeError):
                return False, f"Invalid output type: {output_type}"

    return True, ""


def validate_cover_info(
    cover_info: Any,
) -> tuple[bool, str]:
    """Validate cover information."""
    if not isinstance(cover_info, CoverInfo):
        return False, "Cover information is required."

    if not cover_info.title.strip():
        return False, "Project or paper title is required."

    return True, ""


def validate_presentation_info(
    presentation_info: Any,
) -> tuple[bool, str]:
    """
    Validate presentation information.

    The current shared schema contains presentation preferences,
    while the finalized project requirements also need project-specific
    content. Those additional fields are handled through user_notes
    by the mapper rather than being added to the shared schema.
    """
    if not isinstance(presentation_info, ProjectPresentationInfo):
        return False, "Presentation information is required."

    return True, ""


def validate_academic_info(
    academic_info: Any,
) -> tuple[bool, str]:
    """
    Validate academic information.

    The current shared schema contains academic preferences,
    while the finalized project requirements also need methodology,
    dataset, tools, measurements, results, and limitations. Those
    additional fields are handled through user_notes by the mapper.
    """
    if not isinstance(academic_info, AcademicContentInfo):
        return False, "Academic information is required."

    if not academic_info.citation_style.strip():
        return False, "Citation style is required."

    return True, ""


def validate_tier(tier: str, value: Any) -> tuple[bool, str]:
    """
    Validate a tier using the appropriate validator.
    """
    validators = {
        "topic": validate_topic,
        "output_types": validate_output_types,
        "cover_info": validate_cover_info,
        "presentation_info": validate_presentation_info,
        "academic_info": validate_academic_info,
    }

    validator = validators.get(tier)

    if validator is None:
        return False, f"Unknown input tier: {tier}"

    return validator(value)