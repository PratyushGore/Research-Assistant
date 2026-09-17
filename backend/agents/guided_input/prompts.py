"""
Prompt definitions for the Guided Input Agent.

These prompts are used only for conversational guidance.
Basic validation should remain deterministic and should not depend
on an LLM.
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

Please provide the following project presentation information:

- Target Audience (optional)
- Number of Slides (optional)
- Presentation Tone (optional)
- Key Focus Areas (optional)

Additionally, provide your project-specific information:

- Problem Statement
- Tech Stack
- System Architecture / Approach
- Own Results
- Project Timeline

Do not provide information that has not actually been established for your project.
""".strip()


ACADEMIC_INFO_PROMPT = """
You selected Research Paper generation.

Please provide the following academic information:

- Target Venue or Journal (optional)
- Citation Style (default: APA)
- Methodology Used
- Dataset / Sample Details
- Tools / Instruments
- What Was Measured
- Key Results
- Limitations
- Keywords (optional)

Do not provide information that has not actually been established for your project.
""".strip()


USER_NOTES_PROMPT = """
Do you have any additional instructions or notes for the generated outputs?

This is optional. You can leave it blank if you have nothing else to add.
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