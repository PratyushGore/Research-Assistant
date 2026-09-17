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
    Validate project presentation information.

    Required:
    - problem_statement
    - tech_stack
    - own_architecture_summary
    - own_results_summary

    project_timeline is optional.
    """
    if not isinstance(presentation_info, ProjectPresentationInfo):
        return False, "Presentation information is required."

    if not presentation_info.problem_statement.strip():
        return False, "Problem statement is required."

    if not presentation_info.tech_stack:
        return False, "Tech stack is required."

    if not presentation_info.own_architecture_summary.strip():
        return False, "Own architecture summary is required."

    if not presentation_info.own_results_summary.strip():
        return False, "Own results summary is required."

    return True, ""


def validate_academic_info(
    academic_info: Any,
) -> tuple[bool, str]:
    """
    Validate academic content information.

    Required:
    - methodology
    - dataset_or_sample
    - tools_used
    - what_was_measured
    - key_results

    limitations is optional.
    """
    if not isinstance(academic_info, AcademicContentInfo):
        return False, "Academic information is required."

    if not academic_info.methodology.strip():
        return False, "Methodology is required."

    if not academic_info.dataset_or_sample.strip():
        return False, "Dataset or sample details are required."

    if not academic_info.tools_used:
        return False, "Tools used are required."

    if not academic_info.what_was_measured.strip():
        return False, "What was measured is required."

    if not academic_info.key_results.strip():
        return False, "Key results are required."

    return True, ""


def validate_tier(
    tier: str,
    value: Any,
) -> tuple[bool, str]:
    """Validate a Guided Input tier."""
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