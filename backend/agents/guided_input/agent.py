from dataclasses import dataclass, field
from typing import Any

from backend.schemas.schemas import (
    AcademicContentInfo,
    CoverInfo,
    GuidedInputBundle,
    OutputType,
    ProjectPresentationInfo,
)

from .mapper import build_guided_input_bundle
from .tiers import InputTier, get_required_tiers
from .validators import validate_tier


@dataclass
class GuidedInputSession:
    """
    Stores Guided Input answers for one request/session.

    This is intentionally kept separate from the shared Pydantic schemas
    because the current shared schema does not contain tier-completion
    tracking.
    """

    request_id: str
    data: dict[str, Any] = field(default_factory=dict)
    completed_tiers: set[InputTier] = field(default_factory=set)

    def is_completed(self, tier: InputTier) -> bool:
        return tier in self.completed_tiers

    def mark_completed(self, tier: InputTier) -> None:
        self.completed_tiers.add(tier)

    def save(self, tier: InputTier, value: Any) -> None:
        self.data[tier.value] = value
        self.mark_completed(tier)


class GuidedInputAgent:
    """
    Guided Input Agent.

    Responsibilities:
    - Determine which input tiers are required.
    - Ask each required tier only once per session.
    - Validate collected information deterministically.
    - Store project-specific overflow information in user_notes.
    - Produce a valid GuidedInputBundle when all required information
      has been collected.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, GuidedInputSession] = {}

    def create_session(self, request_id: str) -> GuidedInputSession:
        """Create a new session or return the existing session."""
        if request_id not in self._sessions:
            self._sessions[request_id] = GuidedInputSession(
                request_id=request_id
            )

        return self._sessions[request_id]

    def get_session(self, request_id: str) -> GuidedInputSession:
        """Return an existing session."""
        return self.create_session(request_id)

    def get_required_tiers(
        self,
        output_types: list[OutputType | str],
    ) -> list[InputTier]:
        """Return the required tiers for the selected outputs."""
        normalized_output_types = [
            self._normalize_output_type(value)
            for value in output_types
        ]

        return get_required_tiers(normalized_output_types)

    def next_incomplete_tier(
        self,
        request_id: str,
        output_types: list[OutputType | str],
    ) -> InputTier | None:
        """
        Return the next required tier that has not yet been completed.

        Completed tiers are skipped, so changing or adding output types
        does not cause already-completed tiers to be asked again.
        """
        session = self.get_session(request_id)

        required_tiers = self.get_required_tiers(output_types)

        for tier in required_tiers:
            if not session.is_completed(tier):
                return tier

        return None

    def collect_tier(
        self,
        request_id: str,
        tier: InputTier | str,
        value: Any,
    ) -> tuple[bool, str]:
        """
        Validate and save one tier.

        Returns:
            (True, "") on success
            (False, error_message) on validation failure
        """
        session = self.get_session(request_id)

        if isinstance(tier, InputTier):
            normalized_tier = tier
        else:
            try:
                normalized_tier = InputTier(tier)
            except ValueError:
                return False, f"Unknown input tier: {tier}"

        is_valid, error_message = validate_tier(
            normalized_tier.value,
            value,
        )

        if not is_valid:
            return False, error_message

        session.save(normalized_tier, value)

        return True, ""

    def collect_topic(
        self,
        request_id: str,
        topic: str,
    ) -> tuple[bool, str]:
        """Collect the research topic."""
        return self.collect_tier(
            request_id,
            InputTier.TOPIC,
            topic,
        )

    def collect_output_types(
        self,
        request_id: str,
        output_types: list[OutputType | str],
    ) -> tuple[bool, str]:
        """Collect selected output types."""
        normalized = []

        for value in output_types:
            try:
                normalized.append(self._normalize_output_type(value))
            except ValueError:
                return False, f"Invalid output type: {value}"

        return self.collect_tier(
            request_id,
            InputTier.OUTPUT_TYPES,
            normalized,
        )

    def collect_cover_info(
        self,
        request_id: str,
        cover_info: CoverInfo | dict[str, Any],
    ) -> tuple[bool, str]:
        """Collect cover information."""
        if isinstance(cover_info, dict):
            try:
                cover_info = CoverInfo(**cover_info)
            except Exception as exc:
                return False, f"Invalid cover information: {exc}"

        return self.collect_tier(
            request_id,
            InputTier.COVER_INFO,
            cover_info,
        )

    def collect_presentation_info(
        self,
        request_id: str,
        presentation_info: ProjectPresentationInfo | dict[str, Any],
        project_content: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Collect PPT information.

        presentation_info contains fields supported directly by the
        shared schema.

        project_content contains the project-specific fields that the
        current shared schema does not support directly.
        """
        if isinstance(presentation_info, dict):
            try:
                presentation_info = ProjectPresentationInfo(
                    **presentation_info
                )
            except Exception as exc:
                return False, f"Invalid presentation information: {exc}"

        content = project_content or {}

        required_fields = {
            "problem_statement": "Problem Statement",
            "tech_stack": "Tech Stack",
            "architecture_or_approach": "System Architecture / Approach",
            "own_results": "Own Results",
            "timeline": "Project Timeline",
        }

        missing = [
            label
            for key, label in required_fields.items()
            if not str(content.get(key, "")).strip()
        ]

        if missing:
            return (
                False,
                "Missing required PPT project information: "
                + ", ".join(missing),
            )

        session = self.get_session(request_id)

        session.save(
            InputTier.PRESENTATION_INFO,
            presentation_info,
        )

        session.data["presentation_data"] = content

        return True, ""

    def collect_academic_info(
        self,
        request_id: str,
        academic_info: AcademicContentInfo | dict[str, Any],
        project_content: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Collect Research Paper information.

        academic_info contains fields supported directly by the
        shared schema.

        project_content contains the academic project fields that the
        current shared schema does not support directly.
        """
        if isinstance(academic_info, dict):
            try:
                academic_info = AcademicContentInfo(**academic_info)
            except Exception as exc:
                return False, f"Invalid academic information: {exc}"

        content = project_content or {}

        required_fields = {
            "methodology_used": "Methodology Used",
            "dataset_or_sample_details": "Dataset / Sample Details",
            "tools_or_instruments": "Tools / Instruments",
            "what_was_measured": "What Was Measured",
            "key_results": "Key Results",
            "limitations": "Limitations",
        }

        missing = [
            label
            for key, label in required_fields.items()
            if not str(content.get(key, "")).strip()
        ]

        if missing:
            return (
                False,
                "Missing required academic project information: "
                + ", ".join(missing),
            )

        session = self.get_session(request_id)

        session.save(
            InputTier.ACADEMIC_INFO,
            academic_info,
        )

        session.data["academic_data"] = content

        return True, ""

    def is_complete(
        self,
        request_id: str,
        output_types: list[OutputType | str],
    ) -> bool:
        """Check whether all required Guided Input tiers are complete."""
        session = self.get_session(request_id)

        required_tiers = self.get_required_tiers(output_types)

        return all(
            session.is_completed(tier)
            for tier in required_tiers
        )

    def build_bundle(
        self,
        request_id: str,
    ) -> GuidedInputBundle:
        """
        Build the final GuidedInputBundle.

        Raises ValueError when required information has not yet
        been collected.
        """
        session = self.get_session(request_id)

        topic = session.data.get("topic")
        output_types = session.data.get("output_types")
        cover_info = session.data.get("cover_info")

        if topic is None:
            raise ValueError("Research topic has not been collected.")

        if not output_types:
            raise ValueError("Output types have not been collected.")

        if cover_info is None:
            raise ValueError("Cover information has not been collected.")

        normalized_output_types = [
            self._normalize_output_type(value)
            for value in output_types
        ]

        required_tiers = self.get_required_tiers(
            normalized_output_types
        )

        missing_tiers = [
            tier.value
            for tier in required_tiers
            if not session.is_completed(tier)
        ]

        if missing_tiers:
            raise ValueError(
                "Guided Input is incomplete. Missing tiers: "
                + ", ".join(missing_tiers)
            )

        return build_guided_input_bundle(
            research_topic=topic,
            output_types=normalized_output_types,
            cover_info=cover_info,
            presentation_info=session.data.get(
                "presentation_info"
            ),
            academic_info=session.data.get(
                "academic_info"
            ),
            presentation_data=session.data.get(
                "presentation_data"
            ),
            academic_data=session.data.get(
                "academic_data"
            ),
            user_notes=session.data.get("user_notes"),
        )

    def add_user_notes(
        self,
        request_id: str,
        user_notes: str | None,
    ) -> None:
        """Store optional additional user notes."""
        session = self.get_session(request_id)

        if user_notes and user_notes.strip():
            session.data["user_notes"] = user_notes.strip()

    @staticmethod
    def _normalize_output_type(
        value: OutputType | str,
    ) -> OutputType:
        """Convert an output type value into OutputType."""
        if isinstance(value, OutputType):
            return value

        return OutputType(value)


# Simple default instance for application-level use.
guided_input_agent = GuidedInputAgent()