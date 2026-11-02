"""SQLite sink for per-API-call token accounting.

Three tables, one row per grain:
  api_calls        — one row per HTTP call to the model (several per user turn)
  turns            — one row per user query, keyed by request_id
  tool_invocations — one row per tool executed

plus a `turn_stage_rollup` view answering "tokens per user query, by stage".

Observation only. Every public function swallows its own exceptions: a metrics
failure must never take down a turn. Uses stdlib sqlite3 — no new dependency,
no service.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("agent.tokens.store")

# Off by setting ECOPATH_TOKEN_METRICS=0. On by default: the whole point of
# stage 1 is that normal use produces the numbers.
ENABLED = os.getenv("ECOPATH_TOKEN_METRICS", "1") not in ("0", "false", "False")

DB_PATH = Path(
    os.getenv("ECOPATH_TOKEN_DB", Path(__file__).resolve().parent.parent / "token_metrics.db")
)

_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_calls (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id          TEXT NOT NULL,
    session_id          TEXT,
    round_index         INTEGER,
    ts                  TEXT,
    model               TEXT,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    cached_tokens       INTEGER,
    estimated           INTEGER,
    latency_ms          INTEGER,
    tools_sent          INTEGER,
    tool_names          TEXT,
    finish_reason       TEXT,
    message_count       INTEGER,
    payload_chars       INTEGER,
    seg_system          INTEGER,
    seg_system_base     INTEGER,
    seg_system_coverage INTEGER,
    seg_system_context  INTEGER,
    seg_tool_schemas    INTEGER,
    seg_history         INTEGER,
    seg_user            INTEGER,
    seg_assistant       INTEGER,
    seg_tool_results    INTEGER,
    seg_source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_calls_request ON api_calls(request_id);

CREATE TABLE IF NOT EXISTS turns (
    request_id         TEXT PRIMARY KEY,
    session_id         TEXT,
    ts                 TEXT,
    model              TEXT,
    label              TEXT,
    user_message       TEXT,
    rounds             INTEGER,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cached_tokens      INTEGER,
    tool_result_tokens INTEGER,
    latency_ms         INTEGER,
    resend_multiplier  REAL,
    error              TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);

CREATE TABLE IF NOT EXISTS tool_invocations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    round_index INTEGER,
    ts          TEXT,
    name        TEXT,
    chars       INTEGER,
    est_tokens  INTEGER,
    row_count   INTEGER,
    truncated   INTEGER,
    latency_ms  INTEGER,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tool_request ON tool_invocations(request_id);

-- "Tokens per user query, broken down by stage." Input segments sum to
-- input_total; generation is the output side. Values carry resend
-- multiplicity, because that is what was actually billed.
CREATE VIEW IF NOT EXISTS turn_stage_rollup AS
SELECT
    t.request_id,
    t.session_id,
    t.label,
    t.ts,
    t.model,
    t.user_message,
    t.rounds,
    SUM(c.seg_system)          AS system_prompt,
    SUM(c.seg_system_base)     AS system_base,
    SUM(c.seg_system_coverage) AS system_coverage,
    SUM(c.seg_system_context)  AS system_context,
    SUM(c.seg_tool_schemas)    AS tool_schemas,
    SUM(c.seg_history)         AS history,
    SUM(c.seg_tool_results)    AS tool_results,
    SUM(c.seg_user)            AS user_msg,
    SUM(c.seg_assistant)       AS assistant_msgs,
    SUM(c.input_tokens)        AS input_total,
    SUM(c.output_tokens)       AS generation,
    SUM(c.cached_tokens)       AS cached,
    SUM(c.input_tokens) + SUM(c.output_tokens) AS total_tokens
FROM turns t
JOIN api_calls c USING (request_id)
GROUP BY t.request_id;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL so a reader (the report CLI) never blocks the running server.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _initialized
    if not _initialized:
        conn.executescript(SCHEMA)
        _initialized = True


def _write(sql: str, params: Iterable[Any]) -> None:
    if not ENABLED:
        return
    try:
        with _lock:
            conn = _connect()
            try:
                _ensure_schema(conn)
                conn.execute(sql, tuple(params))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:  # never propagate: metrics must not break a turn
        log.warning("token metrics write failed: %s", e)


def record_api_call(row: dict) -> None:
    cols = [
        "request_id", "session_id", "round_index", "ts", "model",
        "input_tokens", "output_tokens", "cached_tokens", "estimated",
        "latency_ms", "tools_sent", "tool_names", "finish_reason",
        "message_count", "payload_chars",
        "seg_system", "seg_system_base", "seg_system_coverage",
        "seg_system_context", "seg_tool_schemas", "seg_history",
        "seg_user", "seg_assistant", "seg_tool_results", "seg_source",
    ]
    _write(
        f"INSERT INTO api_calls ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [row.get(c) for c in cols],
    )


def record_tool_invocation(row: dict) -> None:
    cols = [
        "request_id", "round_index", "ts", "name", "chars", "est_tokens",
        "row_count", "truncated", "latency_ms", "error",
    ]
    _write(
        f"INSERT INTO tool_invocations ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [row.get(c) for c in cols],
    )


def record_turn(row: dict) -> None:
    cols = [
        "request_id", "session_id", "ts", "model", "label", "user_message",
        "rounds", "input_tokens", "output_tokens", "cached_tokens",
        "tool_result_tokens", "latency_ms", "resend_multiplier", "error",
    ]
    _write(
        f"INSERT OR REPLACE INTO turns ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [row.get(c) for c in cols],
    )


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Read-only helper for the report CLI."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()
