from typing import Any

from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    GuidedInputBundle,
    OutputType,
    ProjectPresentationInfo,
)


def _to_output_type(value: Any) -> OutputType:
    """Convert a string or OutputType value to OutputType."""
    if isinstance(value, OutputType):
        return value

    return OutputType(value)


def _build_presentation_notes(data: dict[str, Any]) -> str:
    """Store project-specific presentation fields not present in the shared schema."""
    fields = [
        ("Problem Statement", data.get("problem_statement")),
        ("Tech Stack", data.get("tech_stack")),
        ("System Architecture / Approach", data.get("architecture_or_approach")),
        ("Own Results", data.get("own_results")),
        ("Project Timeline", data.get("timeline")),
    ]

    lines = [
        "[PRESENTATION PROJECT CONTENT]",
    ]

    for label, value in fields:
        if value is not None and str(value).strip():
            lines.append(f"{label}: {str(value).strip()}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _build_academic_notes(data: dict[str, Any]) -> str:
    """Store academic content fields not present in the shared schema."""
    fields = [
        ("Methodology Used", data.get("methodology_used")),
        ("Dataset / Sample Details", data.get("dataset_or_sample_details")),
        ("Tools / Instruments", data.get("tools_or_instruments")),
        ("What Was Measured", data.get("what_was_measured")),
        ("Key Results", data.get("key_results")),
        ("Limitations", data.get("limitations")),
    ]

    lines = [
        "[ACADEMIC PROJECT CONTENT]",
    ]

    for label, value in fields:
        if value is not None and str(value).strip():
            lines.append(f"{label}: {str(value).strip()}")

    return "\n".join(lines) if len(lines) > 1 else ""


def build_user_notes(
    presentation_data: dict[str, Any] | None = None,
    academic_data: dict[str, Any] | None = None,
    user_notes: str | None = None,
) -> str | None:
    """
    Combine overflow project/academic content with optional user notes.

    These fields are placed in user_notes because the current shared
    GuidedInputBundle schema does not contain dedicated fields for them.
    """
    sections: list[str] = []

    if presentation_data:
        presentation_notes = _build_presentation_notes(presentation_data)
        if presentation_notes:
            sections.append(presentation_notes)

    if academic_data:
        academic_notes = _build_academic_notes(academic_data)
        if academic_notes:
            sections.append(academic_notes)

    if user_notes and user_notes.strip():
        sections.append(f"[USER NOTES]\n{user_notes.strip()}")

    if not sections:
        return None

    return "\n\n".join(sections)


def build_guided_input_bundle(
    research_topic: str,
    output_types: list[OutputType | str],
    cover_info: CoverInfo | dict[str, Any],
    presentation_info: ProjectPresentationInfo | dict[str, Any] | None = None,
    academic_info: AcademicContentInfo | dict[str, Any] | None = None,
    presentation_data: dict[str, Any] | None = None,
    academic_data: dict[str, Any] | None = None,
    user_notes: str | None = None,
) -> GuidedInputBundle:
    """
    Convert collected Guided Input answers into the shared
    GuidedInputBundle schema.

    No fields are added to the shared schema.
    """
    normalized_output_types = [
        _to_output_type(output_type) for output_type in output_types
    ]

    if isinstance(cover_info, dict):
        cover_info = CoverInfo(**cover_info)

    if isinstance(presentation_info, dict):
        presentation_info = ProjectPresentationInfo(**presentation_info)

    if isinstance(academic_info, dict):
        academic_info = AcademicContentInfo(**academic_info)

    combined_notes = build_user_notes(
        presentation_data=presentation_data,
        academic_data=academic_data,
        user_notes=user_notes,
    )

    return GuidedInputBundle(
        research_topic=research_topic.strip(),
        output_types=normalized_output_types,
        cover_info=cover_info,
        presentation_info=presentation_info,
        academic_info=academic_info,
        user_notes=combined_notes,
    )