"""Server-side holding area for chart series the model must never see.

A tool that produces a time series registers the full series here and hands the
model only a compact summary plus the returned `series_ref`. The model reasons
over the summary and emits a chart block carrying the ref; the frontend
resolves it through `/api/chart/{ref}`.

That keeps bulk data out of the context window in *both* directions — the model
neither ingests the points nor has to echo them back into its JSON answer.

In-memory with a TTL, mirroring `agent.session`: same lifetime semantics, no new
service dependency. A ref that has expired resolves to None and the frontend
falls back to the block's summary.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from config import get_settings

logger = logging.getLogger("ecopath.agent.chart_store")

# Charts outlive the turn that made them but not the session that owns them.
CHART_TTL = timedelta(minutes=get_settings().agent_session_ttl_minutes)

# Guards against unbounded growth if eviction never runs (single-process app).
MAX_ENTRIES = 500

_charts: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _evict_expired(now: Optional[datetime] = None) -> int:
    now = now or _now()
    dead = [k for k, v in _charts.items() if now - v["created_at"] > CHART_TTL]
    for k in dead:
        _charts.pop(k, None)
    # Hard ceiling: drop oldest first if something is leaking.
    if len(_charts) > MAX_ENTRIES:
        for k, _ in sorted(_charts.items(), key=lambda kv: kv[1]["created_at"])[
            : len(_charts) - MAX_ENTRIES
        ]:
            _charts.pop(k, None)
    return len(dead)


def put(spec: dict, session_id: str = "") -> str:
    """Store a render spec and return the ref the model will quote."""
    _evict_expired()
    ref = uuid.uuid4().hex[:16]
    _charts[ref] = {"spec": spec, "session_id": session_id, "created_at": _now()}
    return ref


def get(ref: str) -> Optional[dict]:
    """Resolve a ref to its render spec, or None if unknown or expired."""
    entry = _charts.get(ref)
    if entry is None:
        return None
    if _now() - entry["created_at"] > CHART_TTL:
        _charts.pop(ref, None)
        return None
    return entry["spec"]


def count() -> int:
    return len(_charts)


def clear() -> None:
    _charts.clear()


def register_series(
    *,
    chart_type: str,
    title: str,
    series: list[dict],
    x_label: str = "",
    y_label: str = "",
    session_id: str = "",
    **extra: Any,
) -> str:
    """
    Convenience wrapper: stash a chart the frontend can render as-is.

    `series` is the full-fidelity data. Callers hand the model the ref and a
    summary, never this.
    """
    spec = {
        "type": chart_type,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "series": series,
    }
    spec.update(extra)
    return put(spec, session_id=session_id)
