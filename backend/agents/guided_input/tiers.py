from enum import Enum

from backend.schemas.schemas import OutputType


class InputTier(str, Enum):
    TOPIC = "topic"
    OUTPUT_TYPES = "output_types"
    COVER_INFO = "cover_info"
    PRESENTATION_INFO = "presentation_info"
    ACADEMIC_INFO = "academic_info"


def get_required_tiers(output_types: list[OutputType]) -> list[InputTier]:
    """
    Determine which Guided Input tiers are required based on
    the selected output types.

    Rules:
    - Topic and output types are always required.
    - Cover information is always required.
    - Presentation information is required when PPT is selected.
    - Academic information is required when Research Paper is selected.
    """

    required = [
        InputTier.TOPIC,
        InputTier.OUTPUT_TYPES,
        InputTier.COVER_INFO,
    ]

    if OutputType.PPT in output_types:
        required.append(InputTier.PRESENTATION_INFO)

    if OutputType.RESEARCH_PAPER in output_types:
        required.append(InputTier.ACADEMIC_INFO)

    return required