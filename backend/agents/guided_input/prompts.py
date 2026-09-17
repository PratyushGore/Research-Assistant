"""
Prompt definitions for the Guided Input Agent.

These prompts are deterministic user-facing instructions.
They do not require an LLM.
"""

TOPIC_PROMPT = """
Please enter your research topic or research question.

Example:
"AI-based crop disease detection using deep learning"
""".strip()


OUTPUT_TYPES_PROMPT = """
Which output(s) would you like to generate?

You can select one or more:
1. Literature Survey
2. Executive Summary
3. PPT
4. Research Paper
""".strip()


COVER_INFO_PROMPT = """
Please provide the following cover information:

- Project/Paper Title
- Author/Team Names
- Institution/College
- Date (optional)
- Subtitle (optional)
""".strip()


PRESENTATION_INFO_PROMPT = """
You selected PPT generation.

Please provide your project presentation information:

- Problem Statement
- Tech Stack
- Own Architecture Summary
- Own Results Summary
- Project Timeline (optional)

Only provide information that has actually been established
for your project.
""".strip()


ACADEMIC_INFO_PROMPT = """
You selected Research Paper generation.

Please provide your academic content information:

- Methodology
- Dataset / Sample Details
- Tools Used
- What Was Measured
- Key Results
- Limitations (optional)

Only provide information that has actually been established
for your project.
""".strip()


USER_NOTES_PROMPT = """
Do you have any additional instructions or notes for the
generated outputs?

This is optional. You can leave it blank if you have nothing
else to add.
""".strip()


TIER_PROMPTS = {
    "topic": TOPIC_PROMPT,
    "output_types": OUTPUT_TYPES_PROMPT,
    "cover_info": COVER_INFO_PROMPT,
    "presentation_info": PRESENTATION_INFO_PROMPT,
    "academic_info": ACADEMIC_INFO_PROMPT,
}


def get_tier_prompt(tier: str) -> str:
    """
    Return the prompt associated with a Guided Input tier.
    """
    try:
        return TIER_PROMPTS[tier]
    except KeyError as exc:
        raise ValueError(f"Unknown input tier: {tier}") from exc