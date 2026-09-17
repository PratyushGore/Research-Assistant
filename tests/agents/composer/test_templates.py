from backend.agents.composer.templates import (
    OUTPUT_TEMPLATES,
    get_template,
)
from backend.schemas.schemas import OutputType


def test_all_output_types_have_templates():
    assert set(OUTPUT_TEMPLATES.keys()) == {
        OutputType.LITERATURE_SURVEY,
        OutputType.EXECUTIVE_SUMMARY,
        OutputType.PPT,
        OutputType.RESEARCH_PAPER,
    }


def test_literature_survey_template():
    template = get_template(OutputType.LITERATURE_SURVEY)

    assert template.output_type == OutputType.LITERATURE_SURVEY
    assert template.template_id == "literature-survey-v1"
    assert "Abstract" in template.sections
    assert "Thematic Review" in template.sections
    assert "References" in template.sections


def test_executive_summary_template():
    template = get_template(OutputType.EXECUTIVE_SUMMARY)

    assert template.output_type == OutputType.EXECUTIVE_SUMMARY
    assert "Overview" in template.sections
    assert "Key Findings" in template.sections
    assert "Implications" in template.sections


def test_ppt_template():
    template = get_template(OutputType.PPT)

    assert template.output_type == OutputType.PPT
    assert "Problem" in template.sections
    assert "Own Approach/Architecture" in template.sections
    assert "Own Results" in template.sections


def test_research_paper_template():
    template = get_template(OutputType.RESEARCH_PAPER)

    assert template.output_type == OutputType.RESEARCH_PAPER
    assert "Methodology" in template.sections
    assert "Results/Discussion" in template.sections
    assert "References" in template.sections


def test_templates_are_output_template_objects():
    for template in OUTPUT_TEMPLATES.values():
        assert template.template_id
        assert template.output_type in OutputType
        assert len(template.sections) > 0