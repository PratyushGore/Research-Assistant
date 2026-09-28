"""
Session memory layer for the Orchestrator.

Manages in-memory guided-input sessions before the LangGraph execution pipeline.
Thread-safe using standard library threading.RLock.
"""

from collections.abc import Iterator, Mapping
from enum import Enum
import threading
from typing import Any, Optional
import uuid
from pydantic import ValidationError

from backend.agents.guided_input.agent import GuidedInputAgent, guided_input_agent
from backend.agents.guided_input.tiers import InputTier
from backend.schemas.schemas import GuidedInputBundle, OutputType


class SessionStatus(str, Enum):
    """Allowed session lifecycle statuses."""

    COLLECTING = "collecting"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class SessionNotFoundError(KeyError):
    """Raised when a requested session_id does not exist."""

    pass


class SessionIncompleteError(ValueError):
    """Raised when an operation requires a completed session."""

    pass


TIER_RECORD_KEYS: dict[str, str] = {
    InputTier.TOPIC.value: "research_topic",
    InputTier.OUTPUT_TYPES.value: "output_types",
    InputTier.COVER_INFO.value: "cover_info",
    InputTier.PRESENTATION_INFO.value: "presentation_info",
    InputTier.ACADEMIC_INFO.value: "academic_info",
}


class SessionStore(Mapping[str, dict[str, Any]]):
    """
    In-memory session store keyed by session_id.

    Each record holds:
    - session_id: str
    - research_topic: str
    - topic: str (alias)
    - output_types: list[OutputType]
    - cover_info: CoverInfo | None
    - presentation_info: ProjectPresentationInfo | None
    - academic_info: AcademicContentInfo | None
    - user_notes: str | None
    - completed_tiers: list[str]
    - status: str ("collecting", "ready", "running", "done", "error")
    """

    def __init__(self, agent: Optional[GuidedInputAgent] = None) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._agent = agent or guided_input_agent

    def create_session(
        self,
        topic: str,
        output_types: list[OutputType | str],
    ) -> tuple[str, Optional[InputTier]]:
        """
        Generate a unique id, store topic and output types, and mark them complete.

        Returns (session_id, next_tier).
        """
        session_id = str(uuid.uuid4())

        try:
            ok_topic, err_topic, norm_topic = self._agent.collect_topic(session_id, topic)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid topic: {exc}") from exc

        if not ok_topic:
            raise ValueError(f"Invalid topic: {err_topic}")

        try:
            ok_out, err_out, norm_out = self._agent.collect_output_types(session_id, output_types)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid output types: {exc}") from exc

        if not ok_out:
            raise ValueError(f"Invalid output types: {err_out}")

        completed = [InputTier.TOPIC.value, InputTier.OUTPUT_TYPES.value]

        with self._lock:
            next_tier = self._agent.next_incomplete_tier(
                session_id=session_id,
                output_types=norm_out,
                completed_tiers=completed,
            )

            is_complete = self._agent.is_complete(
                session_id=session_id,
                output_types=norm_out,
                completed_tiers=completed,
            )

            status = (
                SessionStatus.READY.value
                if is_complete
                else SessionStatus.COLLECTING.value
            )

            record: dict[str, Any] = {
                "session_id": session_id,
                "research_topic": norm_topic,
                "topic": norm_topic,
                "output_types": norm_out,
                "cover_info": None,
                "presentation_info": None,
                "academic_info": None,
                "user_notes": None,
                "completed_tiers": completed,
                "status": status,
            }

            self._sessions[session_id] = record

            return session_id, next_tier

    def submit_tier(
        self,
        session_id: str,
        tier: InputTier | str,
        value: Any,
    ) -> dict[str, Any]:
        """
        Validate tier answer through GuidedInputAgent.collect_tier.

        On failure: stores nothing, returns error dict.
        On success: stores normalized value, marks tier complete,
                    and returns {ok, error, next_tier, is_complete}.
        """
        with self._lock:
            record = self.get_session(session_id)

            try:
                ok, error_msg, normalized_value = self._agent.collect_tier(
                    session_id,
                    tier,
                    value,
                )
            except (ValidationError, TypeError, ValueError) as exc:
                ok, error_msg, normalized_value = False, str(exc), None

            if not ok:
                next_tier = self._agent.next_incomplete_tier(
                    session_id=session_id,
                    output_types=record["output_types"],
                    completed_tiers=record["completed_tiers"],
                )
                is_complete = self._agent.is_complete(
                    session_id=session_id,
                    output_types=record["output_types"],
                    completed_tiers=record["completed_tiers"],
                )
                return {
                    "ok": False,
                    "error": error_msg,
                    "next_tier": next_tier,
                    "is_complete": is_complete,
                }

            tier_name = tier.value if isinstance(tier, InputTier) else str(tier)
            try:
                canonical_tier = InputTier(tier_name)
                tier_str = canonical_tier.value
            except ValueError:
                tier_str = tier_name

            key = TIER_RECORD_KEYS.get(tier_str, tier_str)
            record[key] = normalized_value
            if tier_str == InputTier.TOPIC.value:
                record["topic"] = normalized_value

            if tier_str not in record["completed_tiers"]:
                record["completed_tiers"].append(tier_str)

            next_tier = self._agent.next_incomplete_tier(
                session_id=session_id,
                output_types=record["output_types"],
                completed_tiers=record["completed_tiers"],
            )

            is_complete = self._agent.is_complete(
                session_id=session_id,
                output_types=record["output_types"],
                completed_tiers=record["completed_tiers"],
            )

            if is_complete:
                record["status"] = SessionStatus.READY.value

            return {
                "ok": True,
                "error": "",
                "next_tier": next_tier,
                "is_complete": is_complete,
            }

    def get_bundle(self, session_id: str) -> GuidedInputBundle:
        """
        Call GuidedInputAgent.build_bundle.
        Raises a clear error if the session is incomplete or unknown.
        """
        with self._lock:
            record = self.get_session(session_id)

            return self._agent.build_bundle(session_id, record)

    def get_session(self, session_id: str) -> dict[str, Any]:
        """
        Return the session record, or raise a clear unknown session error.
        """
        with self._lock:
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("session_id must be a non-empty string.")
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Unknown session: {session_id}")
            return self._sessions[session_id]

    def update_status(self, session_id: str, status: SessionStatus | str) -> None:
        """Update session status."""
        status_value = (
            status.value if isinstance(status, SessionStatus) else str(status)
        )
        valid_statuses = {s.value for s in SessionStatus}
        if status_value not in valid_statuses:
            raise ValueError(
                f"Invalid status '{status_value}'. Expected one of: {sorted(valid_statuses)}"
            )

        with self._lock:
            record = self.get_session(session_id)
            record["status"] = status_value

    def clear(self) -> None:
        """Clear all sessions."""
        with self._lock:
            self._sessions.clear()

    def __getitem__(self, session_id: str) -> dict[str, Any]:
        return self.get_session(session_id)

    def __contains__(self, session_id: object) -> bool:
        with self._lock:
            return session_id in self._sessions

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(list(self._sessions.keys()))

    def get(self, session_id: str, default: Any = None) -> Any:
        with self._lock:
            return self._sessions.get(session_id, default)


# Module-level default instance
session_store = SessionStore()


def create_session(
    topic: str,
    output_types: list[OutputType | str],
) -> tuple[str, Optional[InputTier]]:
    """Create a new session in the default session store."""
    return session_store.create_session(topic, output_types)


def submit_tier(
    session_id: str,
    tier: InputTier | str,
    value: Any,
) -> dict[str, Any]:
    """Submit a tier value to the default session store."""
    return session_store.submit_tier(session_id, tier, value)


def get_bundle(session_id: str) -> GuidedInputBundle:
    """Get the GuidedInputBundle from the default session store."""
    return session_store.get_bundle(session_id)


def get_session(session_id: str) -> dict[str, Any]:
    """Get a session record from the default session store."""
    return session_store.get_session(session_id)
