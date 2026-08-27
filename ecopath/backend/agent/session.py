"""
Research session state — the agent's memory of what the user is currently
researching, plus the conversation history (compressed + raw) that backs it.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from config import get_settings

logger = logging.getLogger("ecopath.agent.session")

SESSION_TTL = timedelta(minutes=get_settings().agent_session_ttl_minutes)
CLEANUP_INTERVAL_SECONDS = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchSession(BaseModel):
    """Everything the agent remembers about one research session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    created_at: datetime = Field(default_factory=_now)
    last_active: datetime = Field(default_factory=_now)

    # What the user is currently researching
    active_species: Optional[str] = None
    active_species_scientific: Optional[str] = None
    active_regions: list[str] = Field(default_factory=list)
    active_year_range: tuple[int, int] = (2014, 2024)

    # What the agent last did
    last_tool_calls: list[str] = Field(default_factory=list)
    last_visualization_types: list[str] = Field(default_factory=list)
    last_key_findings: list[str] = Field(default_factory=list)

    # Conversation management
    turn_count: int = 0
    compressed_history: str = ""
    # Plain OpenAI/Groq-style message dicts for the most recent turns.
    raw_history: list[Any] = Field(default_factory=list)

    # Tracking for topic switches
    all_species_discussed: list[str] = Field(default_factory=list)
    all_regions_discussed: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.last_active = _now()

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or _now()) - self.last_active > SESSION_TTL

    def state_summary(self) -> dict:
        """The compact payload sent to the frontend as the `session_state` SSE event."""
        return {
            "species": self.active_species,
            "species_scientific": self.active_species_scientific,
            "regions": list(self.active_regions),
            "year_range": [self.active_year_range[0], self.active_year_range[1]],
            "turn_count": self.turn_count,
        }

    def to_debug_dict(self) -> dict:
        """Full session state for the debug endpoint."""
        data = self.model_dump(exclude={"raw_history"}, mode="json")
        data["raw_history"] = list(self.raw_history)
        data["raw_history_message_count"] = len(self.raw_history)
        data["compressed_history_chars"] = len(self.compressed_history)
        return data


@dataclass
class ToolCallRecord:
    """One tool invocation made during a turn."""

    name: str
    args: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)


@dataclass
class TurnData:
    """Everything that happened during one completed agent turn."""

    user_message: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    final_blocks: list[dict] = field(default_factory=list)


# ─── Store ────────────────────────────────────────────────────────────────────

_sessions: dict[str, ResearchSession] = {}


def _create_new_session(session_id: str) -> ResearchSession:
    session = ResearchSession(session_id=session_id)
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> tuple[ResearchSession, bool]:
    """
    Return the live session for `session_id` plus a flag saying whether a
    previously-existing session had to be discarded because it expired.

    A session id that was simply never seen before is *not* an expiry — the flag
    is only True when the user is coming back to a session that timed out, which
    is the case the frontend needs to tell them about.
    """
    existing = _sessions.get(session_id)
    if existing is None:
        return _create_new_session(session_id), False

    if existing.is_expired():
        logger.info(f"Session {session_id} expired after {SESSION_TTL}; starting fresh.")
        del _sessions[session_id]
        return _create_new_session(session_id), True

    return existing, False


def peek_session(session_id: str) -> Optional[ResearchSession]:
    """Look up a session without creating one. Used by the debug endpoint."""
    session = _sessions.get(session_id)
    if session is not None and session.is_expired():
        del _sessions[session_id]
        return None
    return session


def delete_session(session_id: str) -> bool:
    return _sessions.pop(session_id, None) is not None


def active_session_count() -> int:
    return len(_sessions)


def cleanup_expired_sessions() -> int:
    now = _now()
    expired = [sid for sid, s in _sessions.items() if s.is_expired(now)]
    for sid in expired:
        del _sessions[sid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired session(s).")
    return len(expired)


async def cleanup_stale_sessions() -> None:
    """Background loop registered on FastAPI startup."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            cleanup_expired_sessions()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Session cleanup error: {e}")
