from typing import Any, Mapping

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


class GuidedInputAgent:
    """
    Stateless Guided Input Agent.

    The Orchestrator owns session memory. This agent only:
    - determines required tiers,
    - checks which tiers are already completed,
    - validates submitted values,
    - builds the final GuidedInputBundle.
    """

    def get_required_tiers(
        self,
        output_types: list[OutputType | str],
    ) -> list[InputTier]:
        """Return the required Guided Input tiers."""
        normalized_output_types = [
            self._normalize_output_type(value)
            for value in output_types
        ]

        return get_required_tiers(normalized_output_types)

    def next_incomplete_tier(
        self,
        session_id: str,
        output_types: list[OutputType | str],
        completed_tiers: set[str] | list[str] | None = None,
    ) -> InputTier | None:
        """
        Return the next required tier that has not been completed.

        Session memory is supplied by the Orchestrator through
        completed_tiers. The agent does not maintain its own memory.
        """
        if not session_id.strip():
            raise ValueError("session_id is required.")

        completed = set(completed_tiers or [])

        required_tiers = self.get_required_tiers(output_types)

        for tier in required_tiers:
            if tier.value not in completed:
                return tier

        return None

    def validate_answer(
        self,
        tier: InputTier | str,
        value: Any,
    ) -> tuple[bool, str]:
        """
        Validate one Guided Input answer without storing it.
        """
        if isinstance(tier, InputTier):
            normalized_tier = tier
        else:
            try:
                normalized_tier = InputTier(tier)
            except ValueError:
                return False, f"Unknown input tier: {tier}"

        return validate_tier(
            normalized_tier.value,
            value,
        )

    def collect_tier(
        self,
        session_id: str,
        tier: InputTier | str,
        value: Any,
    ) -> tuple[bool, str, Any]:
        """
        Validate one tier answer.

        Returns:
            (True, "", normalized_value) on success
            (False, error_message, None) on failure

        The Orchestrator is responsible for storing the returned value.
        """
        if not session_id.strip():
            return False, "session_id is required.", None

        if isinstance(tier, InputTier):
            normalized_tier = tier
        else:
            try:
                normalized_tier = InputTier(tier)
            except ValueError:
                return (
                    False,
                    f"Unknown input tier: {tier}",
                    None,
                )

        normalized_value = self._normalize_value(
            normalized_tier,
            value,
        )

        is_valid, error_message = validate_tier(
            normalized_tier.value,
            normalized_value,
        )

        if not is_valid:
            return False, error_message, None

        return True, "", normalized_value

    def collect_topic(
        self,
        session_id: str,
        topic: str,
    ) -> tuple[bool, str, str | None]:
        """Validate and return the research topic."""
        return self.collect_tier(
            session_id,
            InputTier.TOPIC,
            topic,
        )

    def collect_output_types(
        self,
        session_id: str,
        output_types: list[OutputType | str],
    ) -> tuple[bool, str, list[OutputType] | None]:
        """Validate and normalize selected output types."""
        return self.collect_tier(
            session_id,
            InputTier.OUTPUT_TYPES,
            output_types,
        )

    def collect_cover_info(
        self,
        session_id: str,
        cover_info: CoverInfo | dict[str, Any],
    ) -> tuple[bool, str, CoverInfo | None]:
        """Validate and return cover information."""
        return self.collect_tier(
            session_id,
            InputTier.COVER_INFO,
            cover_info,
        )

    def collect_presentation_info(
        self,
        session_id: str,
        presentation_info: (
            ProjectPresentationInfo | dict[str, Any]
        ),
    ) -> tuple[
        bool,
        str,
        ProjectPresentationInfo | None,
    ]:
        """Validate and return PPT project information."""
        return self.collect_tier(
            session_id,
            InputTier.PRESENTATION_INFO,
            presentation_info,
        )

    def collect_academic_info(
        self,
        session_id: str,
        academic_info: (
            AcademicContentInfo | dict[str, Any]
        ),
    ) -> tuple[
        bool,
        str,
        AcademicContentInfo | None,
    ]:
        """Validate and return research-paper academic information."""
        return self.collect_tier(
            session_id,
            InputTier.ACADEMIC_INFO,
            academic_info,
        )

    def is_complete(
        self,
        session_id: str,
        output_types: list[OutputType | str],
        completed_tiers: set[str] | list[str] | None = None,
    ) -> bool:
        """
        Check whether all required Guided Input tiers are complete.
        """
        if not session_id.strip():
            raise ValueError("session_id is required.")

        completed = set(completed_tiers or [])

        required_tiers = self.get_required_tiers(output_types)

        return all(
            tier.value in completed
            for tier in required_tiers
        )

    def build_bundle(
        self,
        session_id: str,
        state: Mapping[str, Any],
    ) -> GuidedInputBundle:
        """
        Build GuidedInputBundle from values stored in Orchestrator state.

        Expected state keys:
        - research_topic
        - output_types
        - cover_info
        - presentation_info
        - academic_info
        - user_notes
        """
        if not session_id.strip():
            raise ValueError("session_id is required.")

        topic = state.get("research_topic")
        output_types = state.get("output_types")
        cover_info = state.get("cover_info")

        if topic is None:
            raise ValueError(
                "Research topic has not been collected."
            )

        if not output_types:
            raise ValueError(
                "Output types have not been collected."
            )

        if cover_info is None:
            raise ValueError(
                "Cover information has not been collected."
            )

        normalized_output_types = [
            self._normalize_output_type(value)
            for value in output_types
        ]

        required_tiers = self.get_required_tiers(
            normalized_output_types
        )

        completed_tiers = set(
            state.get("completed_tiers", [])
        )

        missing_tiers = [
            tier.value
            for tier in required_tiers
            if tier.value not in completed_tiers
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
            presentation_info=state.get(
                "presentation_info"
            ),
            academic_info=state.get(
                "academic_info"
            ),
            user_notes=state.get("user_notes"),
        )

    @staticmethod
    def _normalize_output_type(
        value: OutputType | str,
    ) -> OutputType:
        """Convert an output type into the canonical enum."""
        if isinstance(value, OutputType):
            return value

        return OutputType(value)

    @staticmethod
    def _normalize_value(
        tier: InputTier,
        value: Any,
    ) -> Any:
        """Normalize input into the shared Pydantic schema types."""

        if tier == InputTier.OUTPUT_TYPES:
            return [
                (
                    item
                    if isinstance(item, OutputType)
                    else OutputType(item)
                )
                for item in value
            ]

        if tier == InputTier.COVER_INFO:
            if isinstance(value, dict):
                return CoverInfo(**value)

        if tier == InputTier.PRESENTATION_INFO:
            if isinstance(value, dict):
                return ProjectPresentationInfo(**value)

        if tier == InputTier.ACADEMIC_INFO:
            if isinstance(value, dict):
                return AcademicContentInfo(**value)

        if tier == InputTier.TOPIC:
            return str(value).strip()

        return value


guided_input_agent = GuidedInputAgent()