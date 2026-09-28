"""
Session memory layer for the Orchestrator.

Bridges decoupled graphs (research_graph and compose_graph) with session-level
caching of research findings, citations, output selections, and guided input tiers.
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
from backend.schemas.schemas import (
    CoverInfo,
    GuidedInputBundle,
    OutputType,
)


class SessionStatus(str, Enum):
    """Allowed session lifecycle statuses."""

    RESEARCHING = "researching"
    RESEARCH_DONE = "research_done"
    COLLECTING_OUTPUTS = "collecting_outputs"
    READY = "ready"
    COMPOSING = "composing"
    DONE = "done"
    ERROR = "error"

    # Backward-compatibility aliases
    COLLECTING = "collecting_outputs"
    RUNNING = "composing"


class SessionNotFoundError(KeyError):
    """Raised when a requested session_id does not exist."""

    pass


class SessionIncompleteError(ValueError):
    """Raised when an operation requires a completed session."""

    pass


class InvalidSessionStateError(ValueError):
    """Raised when an operation is invalid for the current session state."""

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
    - findings: FindingsPacket | dict[str, Any] | None
    - citations: CitationResult | dict[str, Any] | None
    - output_types: list[OutputType]
    - selected_outputs: list[OutputType] (alias)
    - cover_info: CoverInfo | None
    - presentation_info: ProjectPresentationInfo | None
    - academic_info: AcademicContentInfo | None
    - user_notes: str | None
    - completed_tiers: list[str]
    - status: str (from SessionStatus)
    """

    def __init__(self, agent: Optional[GuidedInputAgent] = None) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._agent = agent or guided_input_agent

    def start_research(self, topic: str) -> str:
        """
        Create a new session in 'researching' status with the research topic stored.
        Does not invoke the graph itself. Returns session_id.
        """
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("Research topic is required and must be a non-empty string.")

        session_id = str(uuid.uuid4())
        norm_topic = topic.strip()

        with self._lock:
            record: dict[str, Any] = {
                "session_id": session_id,
                "research_topic": norm_topic,
                "topic": norm_topic,
                "findings": None,
                "citations": None,
                "output_types": [],
                "selected_outputs": [],
                "cover_info": CoverInfo(title=norm_topic),
                "presentation_info": None,
                "academic_info": None,
                "user_notes": None,
                "completed_tiers": [InputTier.TOPIC.value, InputTier.COVER_INFO.value],
                "status": SessionStatus.RESEARCHING.value,
            }
            self._sessions[session_id] = record
            return session_id

    def store_research_results(
        self,
        session_id: str,
        findings: Any,
        citations: Any,
    ) -> None:
        """
        Save findings and citations, and move status to 'research_done'.
        Raises if the session doesn't exist or is already past this stage.
        """
        with self._lock:
            record = self.get_session(session_id)

            if record["status"] != SessionStatus.RESEARCHING.value:
                raise InvalidSessionStateError(
                    f"Cannot store research results for session '{session_id}': "
                    f"current status is '{record['status']}', expected '{SessionStatus.RESEARCHING.value}'."
                )

            if findings is None or citations is None:
                raise ValueError("Both findings and citations must be provided.")

            record["findings"] = findings
            record["citations"] = citations
            record["status"] = SessionStatus.RESEARCH_DONE.value

    def get_research_results(self, session_id: str) -> tuple[Any, Any]:
        """
        Return (findings, citations) for the session.
        Raises if research hasn't completed yet.
        """
        with self._lock:
            record = self.get_session(session_id)

            if (
                record.get("findings") is None
                or record.get("citations") is None
                or record["status"] == SessionStatus.RESEARCHING.value
            ):
                raise InvalidSessionStateError(
                    f"Research has not completed yet for session '{session_id}' "
                    f"(current status: '{record['status']}')."
                )

            return record["findings"], record["citations"]

    def select_outputs(
        self,
        session_id: str,
        output_types: list[OutputType | str],
    ) -> Optional[InputTier]:
        """
        Store selected outputs, compute required tiers, move status to
        'collecting_outputs' (or 'ready' if no extra tiers needed),
        and return the first incomplete tier (or None if none needed).

        Raises if research is not done yet.
        """
        with self._lock:
            record = self.get_session(session_id)

            if (
                record["status"] == SessionStatus.RESEARCHING.value
                or record.get("findings") is None
                or record.get("citations") is None
            ):
                raise InvalidSessionStateError(
                    f"Cannot select outputs: research is not completed yet for session '{session_id}' "
                    f"(current status: '{record['status']}')."
                )

            if record["status"] in (SessionStatus.COMPOSING.value, SessionStatus.DONE.value):
                raise InvalidSessionStateError(
                    f"Cannot select outputs: session '{session_id}' is already in '{record['status']}' state."
                )

            try:
                ok_out, err_out, norm_out = self._agent.collect_output_types(session_id, output_types)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid output types: {exc}") from exc

            if not ok_out:
                raise ValueError(f"Invalid output types: {err_out}")

            record["output_types"] = norm_out
            record["selected_outputs"] = norm_out

            if InputTier.OUTPUT_TYPES.value not in record["completed_tiers"]:
                record["completed_tiers"].append(InputTier.OUTPUT_TYPES.value)

            next_tier = self._agent.next_incomplete_tier(
                session_id=session_id,
                output_types=norm_out,
                completed_tiers=record["completed_tiers"],
            )

            is_complete = self._agent.is_complete(
                session_id=session_id,
                output_types=norm_out,
                completed_tiers=record["completed_tiers"],
            )

            if is_complete:
                record["status"] = SessionStatus.READY.value
            else:
                record["status"] = SessionStatus.COLLECTING_OUTPUTS.value

            return next_tier

    def submit_tier(
        self,
        session_id: str,
        tier: InputTier | str,
        value: Any,
    ) -> dict[str, Any]:
        """
        Validate tier answer through GuidedInputAgent.collect_tier.
        Only callable once select_outputs has been called for that session.
        """
        with self._lock:
            record = self.get_session(session_id)

            if (
                record.get("findings") is None
                or record["status"] == SessionStatus.RESEARCHING.value
            ):
                raise InvalidSessionStateError(
                    f"Cannot submit tier: research has not completed yet for session '{session_id}'."
                )

            if (
                not record.get("output_types")
                or InputTier.OUTPUT_TYPES.value not in record.get("completed_tiers", [])
            ):
                raise InvalidSessionStateError(
                    f"Cannot submit tier: outputs have not been selected yet for session '{session_id}'."
                )

            if record["status"] in (SessionStatus.COMPOSING.value, SessionStatus.DONE.value):
                raise InvalidSessionStateError(
                    f"Cannot submit tier: session '{session_id}' is already in '{record['status']}' state."
                )

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
                record["research_topic"] = normalized_value

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
            else:
                record["status"] = SessionStatus.COLLECTING_OUTPUTS.value

            return {
                "ok": True,
                "error": "",
                "next_tier": next_tier,
                "is_complete": is_complete,
            }

    def get_bundle(self, session_id: str) -> GuidedInputBundle:
        """
        Call GuidedInputAgent.build_bundle.
        Raises a clear error if research hasn't completed yet,
        if outputs have not been selected yet, or if the session is incomplete or unknown.
        """
        with self._lock:
            record = self.get_session(session_id)

            if (
                record.get("findings") is None
                or record["status"] == SessionStatus.RESEARCHING.value
            ):
                raise InvalidSessionStateError(
                    f"Cannot get bundle: research has not completed yet for session '{session_id}'."
                )

            if (
                not record.get("output_types")
                or InputTier.OUTPUT_TYPES.value not in record.get("completed_tiers", [])
            ):
                raise InvalidSessionStateError(
                    f"Cannot get bundle: outputs have not been selected yet for session '{session_id}'."
                )

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

    def create_session(
        self,
        topic: str,
        output_types: list[OutputType | str],
    ) -> tuple[str, Optional[InputTier]]:
        """
        Legacy helper for creating a session with topic and output types.
        """
        session_id = self.start_research(topic)
        try:
            ok_out, err_out, norm_out = self._agent.collect_output_types(session_id, output_types)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid output types: {exc}") from exc
        if not ok_out:
            raise ValueError(f"Invalid output types: {err_out}")

        with self._lock:
            record = self._sessions[session_id]
            record["output_types"] = norm_out
            record["selected_outputs"] = norm_out
            if InputTier.OUTPUT_TYPES.value not in record["completed_tiers"]:
                record["completed_tiers"].append(InputTier.OUTPUT_TYPES.value)
            next_tier = self._agent.next_incomplete_tier(
                session_id=session_id,
                output_types=norm_out,
                completed_tiers=record["completed_tiers"],
            )
            return session_id, next_tier

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


def start_research(topic: str) -> str:
    """Create a new session in researching status in the default session store."""
    return session_store.start_research(topic)


def store_research_results(
    session_id: str,
    findings: Any,
    citations: Any,
) -> None:
    """Store research findings and citations in the default session store."""
    return session_store.store_research_results(session_id, findings, citations)


def get_research_results(session_id: str) -> tuple[Any, Any]:
    """Retrieve research findings and citations from the default session store."""
    return session_store.get_research_results(session_id)


def select_outputs(
    session_id: str,
    output_types: list[OutputType | str],
) -> Optional[InputTier]:
    """Select output types for a session in the default session store."""
    return session_store.select_outputs(session_id, output_types)


def create_session(
    topic: str,
    output_types: list[OutputType | str],
) -> tuple[str, Optional[InputTier]]:
    """Create a new session in the default session store (legacy)."""
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


__all__ = [
    "SessionStatus",
    "SessionNotFoundError",
    "SessionIncompleteError",
    "InvalidSessionStateError",
    "SessionStore",
    "session_store",
    "start_research",
    "store_research_results",
    "get_research_results",
    "select_outputs",
    "submit_tier",
    "get_bundle",
    "get_session",
    "create_session",
]
