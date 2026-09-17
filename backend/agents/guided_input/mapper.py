from typing import Any

from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    GuidedInputBundle,
    OutputType,
    ProjectPresentationInfo,
)


def _to_output_type(value: Any) -> OutputType:
    if isinstance(value, OutputType):
        return value
    return OutputType(value)


def build_guided_input_bundle(
    research_topic: str,
    output_types: list[OutputType | str],
    cover_info: CoverInfo | dict[str, Any],
    presentation_info: ProjectPresentationInfo | dict[str, Any] | None = None,
    academic_info: AcademicContentInfo | dict[str, Any] | None = None,
    user_notes: str | None = None,
) -> GuidedInputBundle:

    normalized_output_types = [
        _to_output_type(output_type)
        for output_type in output_types
    ]

    if isinstance(cover_info, dict):
        cover_info = CoverInfo(**cover_info)

    if isinstance(presentation_info, dict):
        presentation_info = ProjectPresentationInfo(**presentation_info)

    if isinstance(academic_info, dict):
        academic_info = AcademicContentInfo(**academic_info)

    return GuidedInputBundle(
        cover_info=cover_info,
        project_presentation_info=presentation_info,
        academic_content_info=academic_info,
    )