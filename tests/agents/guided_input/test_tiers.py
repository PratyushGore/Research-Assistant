from backend.agents.guided_input.tiers import (
    InputTier,
    get_required_tiers,
)
from backend.schemas.schemas import OutputType


def test_literature_survey_requires_basic_tiers():
    tiers = get_required_tiers(
        [OutputType.LITERATURE_SURVEY]
    )

    assert tiers == [
        InputTier.TOPIC,
        InputTier.OUTPUT_TYPES,
        InputTier.COVER_INFO,
    ]


def test_ppt_requires_presentation_info():
    tiers = get_required_tiers(
        [OutputType.PPT]
    )

    assert InputTier.PRESENTATION_INFO in tiers


def test_research_paper_requires_academic_info():
    tiers = get_required_tiers(
        [OutputType.RESEARCH_PAPER]
    )

    assert InputTier.ACADEMIC_INFO in tiers


def test_multiple_outputs_require_union_of_tiers():
    tiers = get_required_tiers(
        [
            OutputType.PPT,
            OutputType.RESEARCH_PAPER,
        ]
    )

    assert InputTier.TOPIC in tiers
    assert InputTier.OUTPUT_TYPES in tiers
    assert InputTier.COVER_INFO in tiers
    assert InputTier.PRESENTATION_INFO in tiers
    assert InputTier.ACADEMIC_INFO in tiers