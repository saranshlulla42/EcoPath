"""
History compression.

Raw history grows by several thousand tokens a turn, most of it tool-result data
the model has already consumed and written up. We keep the last two turns at full
fidelity and fold everything older into a plain-text summary that rides along at
the head of the conversation.

Summarization is heuristic — no extra LLM call. The summaries are context for a
model, not prose for a human.
"""

import json
import logging

from agent.content_utils import extract_text, is_turn_start
from agent.session import ResearchSession

logger = logging.getLogger("ecopath.agent.history_compressor")

RAW_TURNS_KEPT = 2
MAX_COMPRESSED_CHARS = 6000
MAX_SUMMARIZED_ARG_LIST = 3


def turn_start_indices(history: list[dict]) -> list[int]:
    """Indices in the history where each conversation turn begins."""
    return [i for i, message in enumerate(history) if is_turn_start(message)]


def count_complete_turns(history: list[dict]) -> int:
    return len(turn_start_indices(history))


def summarize_args(args: dict) -> str:
    """Render tool call arguments compactly. Keys are sorted for a stable summary."""
    pieces = []
    for k in sorted((args or {}).keys()):
        v = args[k]
        if isinstance(v, (list, tuple)):
            shown = ",".join(f'"{x}"' for x in list(v)[:MAX_SUMMARIZED_ARG_LIST])
            if len(v) > MAX_SUMMARIZED_ARG_LIST:
                shown += ",…"
            pieces.append(f"{k}=[{shown}]")
        else:
            pieces.append(f'{k}="{v}"')
    return ", ".join(pieces)


def summarize_tool_result(result: dict) -> str:
    """Collapse a tool result to its headline facts, dropping the raw data arrays."""
    if not isinstance(result, dict):
        return "data returned"

    parts = []
    if result.get("species"):
        parts.append(str(result["species"]))
    if result.get("conservation_status"):
        parts.append(f"status {result['conservation_status']}")
    if "total_records" in result:
        parts.append(f"{result['total_records']} total records")
    if "total_anomalies" in result:
        parts.append(f"{result['total_anomalies']} anomalies found")
    if "is_migratory" in result:
        parts.append("migratory" if result["is_migratory"] else "resident species")
    if result.get("region_name"):
        parts.append(f"region {result['region_name']}")

    data = result.get("data")
    if isinstance(data, list):
        regions = [d.get("region") for d in data if isinstance(d, dict) and d.get("region")]
        if regions:
            parts.append(f"{len(data)} region(s): {', '.join(str(r) for r in regions[:5])}")
        else:
            parts.append(f"{len(data)} region(s) of data returned")

    anomalies = result.get("anomalies")
    if isinstance(anomalies, list) and anomalies:
        severities = [str(a.get("severity", "?")) for a in anomalies if isinstance(a, dict)]
        years = [str(a.get("year")) for a in anomalies if isinstance(a, dict) and a.get("year")]
        parts.append(f"severities: {', '.join(severities[:6])}")
        if years:
            parts.append(f"years {', '.join(years[:6])}")

    yearly = result.get("yearly_data")
    if isinstance(yearly, list) and yearly:
        years = [str(d.get("year", "?")) for d in yearly if isinstance(d, dict)]
        parts.append(f"years {years[0]}-{years[-1]}")

    for key in ("species_a", "species_b"):
        value = result.get(key)
        if isinstance(value, dict) and value.get("name"):
            parts.append(f"{value['name']} ({value.get('conservation_status', 'status unknown')})")

    routes = result.get("routes")
    if isinstance(routes, list) and routes:
        parts.append(f"{len(routes)} migration route(s)")

    if result.get("error"):
        parts.append(f"Error: {result['error']}")
    if result.get("note"):
        parts.append(str(result["note"]))

    summary = "; ".join(parts) if parts else "data returned"
    return summary[:400]


def summarize_turn(messages: list[dict]) -> str:
    """Produce a short plain-text summary of one conversation turn."""
    parts: list[str] = []

    for msg in messages:
        if is_turn_start(msg):
            parts.append(f"User asked: {extract_text(msg)}")
            break

    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                parts.append(f"Agent called {fn.get('name', '?')}({summarize_args(args)})")
        elif role == "tool":
            try:
                result = json.loads(msg.get("content") or "{}")
            except json.JSONDecodeError:
                result = {}
            parts.append(f"Result from {msg.get('name', '?')}: {summarize_tool_result(result)}")

    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        text = extract_text(msg)
        if not text or not text.lstrip().startswith("{"):
            continue
        try:
            blocks = json.loads(text).get("blocks", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "narrative":
                content = block.get("content", "")
                first_sentences = ". ".join(content.split(". ")[:2]).strip()
                if first_sentences:
                    parts.append(f"Agent concluded: {first_sentences.rstrip('.')}.")
                break
        break

    return " | ".join(parts)


def trim_compressed_history(compressed: str) -> str:
    """Drop the oldest turn summaries until the string fits the budget."""
    if len(compressed) <= MAX_COMPRESSED_CHARS:
        return compressed

    while len(compressed) > MAX_COMPRESSED_CHARS:
        split_point = compressed.find("\n\n")
        if split_point == -1:
            # A single oversized summary — keep its tail.
            return compressed[-MAX_COMPRESSED_CHARS:]
        compressed = compressed[split_point + 2:]

    return compressed


def maybe_compress_history(session: ResearchSession) -> bool:
    """
    Fold turns older than the last `RAW_TURNS_KEPT` into `compressed_history`.
    Returns True if anything was compressed.
    """
    compressed_any = False

    while True:
        starts = turn_start_indices(session.raw_history)

        if len(starts) <= RAW_TURNS_KEPT:
            break

        # Everything from the first turn start up to the second is one turn.
        # Anything preceding the first start is a stray fragment; sweep it along.
        end = starts[1]
        oldest_turn = session.raw_history[:end]

        turn_summary = summarize_turn(oldest_turn)
        if turn_summary:
            session.compressed_history = (
                f"{session.compressed_history}\n\n{turn_summary}"
                if session.compressed_history
                else turn_summary
            )

        session.raw_history = session.raw_history[end:]
        compressed_any = True

    if compressed_any:
        session.compressed_history = trim_compressed_history(session.compressed_history)
        logger.debug(
            f"Session {session.session_id}: compressed history now "
            f"{len(session.compressed_history)} chars, "
            f"{len(session.raw_history)} raw messages."
        )

    return compressed_any
