"""Per-call and per-turn token accounting for the agent loop.

Grain: one record per *API call* (an agent turn makes several), grouped by a
`request_id` so the rounds of one user query roll up together. Each record
carries input/output/cached tokens, model, latency, and the tools invoked, plus
an attribution of the input tokens across the stages that produced them —
system prompt, tool schemas, history, tool results, current message.

Emits JSON log lines on the `agent.tokens` logger and persists to SQLite via
`token_store`. Observation only — nothing here changes agent behaviour.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent import token_store

log = logging.getLogger("agent.tokens")

# Tool results larger than this get their own warning line.
SIZE_WARN_CHARS = 8_000

# Fallback only, for when the provider omits usage. Treat as an estimate.
CHARS_PER_TOKEN = 4


def _resolve_counter():
    """
    Prefer a real BPE tokenizer for the stage split; fall back to chars/4.

    Only the *split* depends on this — every segment is rescaled to the
    provider's reported prompt_tokens, so the totals are exact either way.
    `pip install tiktoken` sharpens the breakdown; nothing requires it.
    """
    try:
        import tiktoken

        for name in ("o200k_harmony", "o200k_base", "cl100k_base"):
            try:
                enc = tiktoken.get_encoding(name)
                return (lambda s: len(enc.encode(s, disallowed_special=()))), f"tiktoken:{name}"
            except Exception:
                continue
    except Exception:
        pass
    return (lambda s: len(s) // CHARS_PER_TOKEN), f"chars/{CHARS_PER_TOKEN}"


_count, TOKEN_SOURCE = _resolve_counter()

# The segments input tokens are attributed to, in report order.
SEGMENTS = (
    "system_base",
    "system_coverage",
    "system_context",
    "tool_schemas",
    "history",
    "user",
    "assistant",
    "tool_results",
)


def _sizeof(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return len(str(obj))


def _tokens_of(obj: Any) -> int:
    try:
        return _count(obj if isinstance(obj, str) else json.dumps(obj, default=str))
    except Exception:
        return _sizeof(obj) // CHARS_PER_TOKEN


def _normalize(raw: dict[str, int], target: int) -> dict[str, int]:
    """
    Scale locally-counted segments so they sum exactly to `target`, the
    provider's real prompt_tokens. Keeps the headline number truthful even
    though the split is approximate; the residual lands on the largest segment.
    """
    total = sum(raw.values())
    if total <= 0 or target <= 0:
        return {k: 0 for k in raw}
    scaled = {k: int(round(v * target / total)) for k, v in raw.items()}
    residual = target - sum(scaled.values())
    if residual and scaled:
        biggest = max(scaled, key=lambda k: scaled[k])
        scaled[biggest] += residual
    return scaled


@dataclass
class RoundUsage:
    index: int
    prompt_tokens: int | None
    completion_tokens: int | None
    message_count: int
    payload_chars: int
    tools_sent: bool
    tool_calls: list[str] = field(default_factory=list)
    latency_ms: int = 0
    estimated: bool = False
    # Groq caches prompt prefixes automatically on gpt-oss models and bills
    # cached input at 50%. Without this, prompt_tokens cannot be turned into a
    # cost, and a cache hit looks identical to a smaller prompt.
    cached_tokens: int = 0
    segments: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None


@dataclass
class ToolResultRecord:
    round_index: int
    name: str
    chars: int
    est_tokens: int
    row_count: int | None = None
    truncated: bool | None = None
    latency_ms: int | None = None
    error: str | None = None


class TurnMeter:
    """Accumulates usage across the API calls of a single user turn."""

    def __init__(
        self,
        session_id: str,
        model: str,
        *,
        request_id: str | None = None,
        user_message: str = "",
        label: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.model = model
        # Groups every API call of this user turn under one id.
        self.request_id = request_id or uuid.uuid4().hex
        self.user_message = user_message
        self.label = label
        self.rounds: list[RoundUsage] = []
        self.tool_results: list[ToolResultRecord] = []
        self._turn_t0 = time.perf_counter()
        self._round_t0 = self._turn_t0
        # Layout of the messages array, for stage attribution.
        self._user_index: int | None = None
        self._coverage_tokens = 0
        self._schema_tokens = 0

    def set_layout(
        self,
        *,
        user_index: int | None = None,
        coverage: str | None = None,
        tool_schemas: Any = None,
    ) -> None:
        """
        Describe how the messages array is laid out so input tokens can be
        attributed. `coverage` is the stable tail of the cached head; the
        per-turn session context arrives as its own system message and is
        counted from the array.

        Callable more than once: the prompt parts are known where the prompt is
        built, the message layout only inside the loop. `user_index` is the
        position of this turn's user message in the array.
        """
        if user_index is not None:
            self._user_index = user_index
        if coverage is not None:
            self._coverage_tokens = _tokens_of(coverage) if coverage else 0
        if tool_schemas is not None:
            self._schema_tokens = _tokens_of(tool_schemas) if tool_schemas else 0

    def start_round(self) -> None:
        self._round_t0 = time.perf_counter()

    def _raw_segments(self, messages: list[dict], tools_sent: bool) -> dict[str, int]:
        raw = {k: 0 for k in SEGMENTS}
        user_idx = self._user_index

        for i, msg in enumerate(messages):
            n = _tokens_of(msg)
            role = msg.get("role")
            if i == 0 and role == "system":
                # The cacheable head: static contract plus stable coverage.
                cov = min(self._coverage_tokens, n)
                raw["system_coverage"] += cov
                raw["system_base"] += max(n - cov, 0)
            elif role == "system":
                # The per-turn session context, which now rides outside the
                # cached prefix rather than mutating it.
                raw["system_context"] += n
            elif role == "tool":
                raw["tool_results"] += n
            elif user_idx is not None and i == user_idx:
                raw["user"] += n
            elif user_idx is not None and i < user_idx:
                raw["history"] += n
            elif user_idx is None and role == "user":
                raw["history"] += n
            else:
                raw["assistant"] += n

        if tools_sent:
            raw["tool_schemas"] = self._schema_tokens
        return raw

    def record_call(
        self,
        response: Any,
        messages: list[dict],
        *,
        tools_sent: bool,
        tool_calls: list[str] | None = None,
    ) -> None:
        payload_chars = _sizeof(messages)
        usage = getattr(response, "usage", None)

        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        estimated = prompt_tokens is None

        if estimated:
            prompt_tokens = payload_chars // CHARS_PER_TOKEN

        # usage.prompt_tokens_details.cached_tokens — present on Groq's gpt-oss
        # models, absent elsewhere, so treat a missing value as zero rather
        # than as unknown.
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached_tokens = getattr(details, "cached_tokens", None) or 0

        finish_reason = None
        try:
            finish_reason = response.choices[0].finish_reason
        except Exception:
            pass

        segments = _normalize(self._raw_segments(messages, tools_sent), prompt_tokens or 0)
        latency_ms = int((time.perf_counter() - self._round_t0) * 1000)
        round_index = len(self.rounds)

        self.rounds.append(
            RoundUsage(
                index=round_index,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                message_count=len(messages),
                payload_chars=payload_chars,
                tools_sent=tools_sent,
                tool_calls=tool_calls or [],
                latency_ms=latency_ms,
                estimated=estimated,
                cached_tokens=cached_tokens,
                segments=segments,
                finish_reason=finish_reason,
            )
        )

        record = {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "round_index": round_index,
            "ts": token_store.utcnow(),
            "model": self.model,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
            "estimated": int(estimated),
            "latency_ms": latency_ms,
            "tools_sent": int(tools_sent),
            "tool_names": json.dumps(tool_calls or []),
            "finish_reason": finish_reason,
            "message_count": len(messages),
            "payload_chars": payload_chars,
            "seg_system": segments["system_base"]
            + segments["system_coverage"]
            + segments["system_context"],
            "seg_system_base": segments["system_base"],
            "seg_system_coverage": segments["system_coverage"],
            "seg_system_context": segments["system_context"],
            "seg_tool_schemas": segments["tool_schemas"],
            "seg_history": segments["history"],
            "seg_user": segments["user"],
            "seg_assistant": segments["assistant"],
            "seg_tool_results": segments["tool_results"],
            "seg_source": TOKEN_SOURCE,
        }
        token_store.record_api_call(record)
        log.info("api_call %s", json.dumps(record))

    def record_tool_result(
        self,
        name: str,
        result: Any,
        *,
        latency_ms: int | None = None,
    ) -> None:
        chars = _sizeof(result)
        row_count = None
        truncated = None
        error = None
        if isinstance(result, dict):
            row_count = result.get("row_count")
            if row_count is None and isinstance(result.get("rows"), list):
                row_count = len(result["rows"])
            truncated = result.get("truncated")
            error = result.get("error")

        record = ToolResultRecord(
            round_index=max(len(self.rounds) - 1, 0),
            name=name,
            chars=chars,
            est_tokens=chars // CHARS_PER_TOKEN,
            row_count=row_count,
            truncated=truncated,
            latency_ms=latency_ms,
            error=str(error) if error is not None else None,
        )
        self.tool_results.append(record)

        token_store.record_tool_invocation(
            {
                "request_id": self.request_id,
                "round_index": record.round_index,
                "ts": token_store.utcnow(),
                "name": name,
                "chars": chars,
                "est_tokens": record.est_tokens,
                "row_count": row_count,
                "truncated": None if truncated is None else int(bool(truncated)),
                "latency_ms": latency_ms,
                "error": record.error,
            }
        )

        if chars >= SIZE_WARN_CHARS:
            log.warning(
                "fat_tool_result %s",
                json.dumps(
                    {
                        "request_id": self.request_id,
                        "session_id": self.session_id,
                        "tool": name,
                        "chars": chars,
                        "est_tokens": record.est_tokens,
                        "row_count": row_count,
                        "truncated": truncated,
                    }
                ),
            )

    def emit(self, error: str | None = None) -> dict:
        prompts = [r.prompt_tokens or 0 for r in self.rounds]
        total_prompt = sum(prompts)
        first_prompt = prompts[0] if prompts else 0
        total_completion = sum(r.completion_tokens or 0 for r in self.rounds)
        total_cached = sum(r.cached_tokens for r in self.rounds)

        tool_tokens: dict[str, int] = {}
        tool_calls_by_name: dict[str, int] = {}
        for t in self.tool_results:
            tool_tokens[t.name] = tool_tokens.get(t.name, 0) + t.est_tokens
            tool_calls_by_name[t.name] = tool_calls_by_name.get(t.name, 0) + 1

        stages = {k: sum(r.segments.get(k, 0) for r in self.rounds) for k in SEGMENTS}
        latency_ms = int((time.perf_counter() - self._turn_t0) * 1000)
        resend = round(total_prompt / first_prompt, 2) if first_prompt else None

        payload = {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "model": self.model,
            "label": self.label,
            "rounds": len(self.rounds),
            # The headline number: total input tokens billed for this one turn.
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            # Cached input bills at 50% on Groq. Billable-equivalent input is
            # therefore total_prompt - (total_cached / 2).
            "total_cached_tokens": total_cached,
            "cache_hit_rate": round(total_cached / total_prompt, 3)
            if total_prompt
            else None,
            # Round 0's prompt. On a first turn this is the fixed floor
            # (system prompt + tool schemas) plus the user message.
            "round0_prompt_tokens": first_prompt,
            # >1.0 means the loop is resending earlier context. This is the
            # direct measurement of the quadratic-growth sink.
            "resend_multiplier": resend,
            "per_round_prompt_tokens": prompts,
            # Input tokens attributed across the stages that produced them.
            "stage_tokens": stages,
            "token_source": TOKEN_SOURCE,
            "tools_used": [t.name for t in self.tool_results],
            # Summed per name, not last-wins: a tool called on several rounds
            # (run_sql especially) would otherwise report only its final call
            # and understate exactly the number this stage exists to measure.
            "tool_result_tokens": tool_tokens,
            "tool_result_calls": tool_calls_by_name,
            # Compare against total_prompt_tokens to see whether tool results
            # or the fixed prefix dominate the turn.
            "total_tool_result_tokens": sum(tool_tokens.values()),
            "largest_tool_result": max(
                (t.est_tokens for t in self.tool_results), default=0
            ),
            "turn_latency_ms": latency_ms,
            "estimated": any(r.estimated for r in self.rounds),
            "error": error,
        }

        token_store.record_turn(
            {
                "request_id": self.request_id,
                "session_id": self.session_id,
                "ts": token_store.utcnow(),
                "model": self.model,
                "label": self.label,
                "user_message": self.user_message,
                "rounds": len(self.rounds),
                "input_tokens": total_prompt,
                "output_tokens": total_completion,
                "cached_tokens": total_cached,
                "tool_result_tokens": sum(tool_tokens.values()),
                "latency_ms": latency_ms,
                "resend_multiplier": resend,
                "error": error,
            }
        )
        log.info("turn_usage %s", json.dumps(payload))
        return payload
