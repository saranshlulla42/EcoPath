import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from groq import AsyncGroq

from config import get_settings
from agent.data_coverage import get_coverage_summary
from agent.history_compressor import maybe_compress_history
from agent.message_builder import build_history
from agent.response_parser import parse_agent_response
from agent.session import (
    ResearchSession,
    ToolCallRecord,
    TurnData,
    delete_session,
    get_session,
)
from agent.state_extractor import update_session_state
from agent.system_prompt import build_context_message, build_system_prompt
from agent.token_logger import TurnMeter
from agent.tool_declarations import agent_tools
from agent.tools import (
    compare_species,
    correlate_weather,
    describe_dataset,
    list_species,
    query_anomalies,
    query_migration,
    query_population,
    rank_regions,
    run_sql,
)

logger = logging.getLogger("ecopath.agent.agent_loop")
settings = get_settings()

client = AsyncGroq(api_key=settings.groq_api_key)

# Read once at module level: the turn meter needs the model name in
# `run_agent_turn`, where `_execute_agent_loop`'s locals are not in scope.
AGENT_MODEL = getattr(settings, "agent_model", "llama-3.3-70b-versatile")

# We map the function names to the actual python functions
TOOL_FUNCTIONS = {
    "query_population": query_population,
    "query_anomalies": query_anomalies,
    "query_migration": query_migration,
    "compare_species": compare_species,
    "correlate_weather": correlate_weather,
    "describe_dataset": describe_dataset,
    "list_species": list_species,
    "rank_regions": rank_regions,
    "run_sql": run_sql,
}

ERROR_BLOCKS = {
    "model": "I'm sorry, I encountered an error communicating with the AI model.",
    "tools": "I'm sorry, I encountered an error sending data back to the AI model.",
}
GENERIC_ERROR = "I'm sorry, something went wrong while answering that."


@dataclass
class AgentTurnResult:
    """What one agent turn produced, plus the session state it left behind."""

    blocks: List[Dict[str, Any]]
    session_state: Dict[str, Any]
    session_expired: bool = False
    # Groups this turn's API calls in the token metrics tables.
    request_id: Optional[str] = None


def _assistant_message_dict(message) -> dict:
    """Turn a Groq `ChatCompletionMessage` into the plain dict we store/replay."""
    msg: dict = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return msg


def _error_blocks(kind: str) -> List[Dict[str, Any]]:
    return [
        {"type": "narrative", "content": ERROR_BLOCKS.get(kind, GENERIC_ERROR)},
        {"type": "follow_ups", "suggestions": ["Try asking that again"]},
    ]


CAP_NOTICE = (
    "**Note:** I stopped after {rounds} rounds of data lookups, so this answer is "
    "based only on what I had gathered by then and may be incomplete. That usually "
    "means a tool kept failing or the question needed more steps than the limit "
    "allows. Try asking a narrower version of it."
)


def _with_cap_notice(blocks: List[Dict[str, Any]], rounds: int) -> List[Dict[str, Any]]:
    """
    Say plainly that the round cap cut the work short.

    Hitting the cap is not a silent truncation: the user gets a partial answer
    and is told it is partial. The notice goes just before the follow-ups, so it
    reads as a closing caveat rather than burying the analysis.
    """
    notice = {"type": "narrative", "content": CAP_NOTICE.format(rounds=rounds)}
    out = list(blocks)
    for i, block in enumerate(out):
        if block.get("type") == "follow_ups":
            out.insert(i, notice)
            return out
    out.append(notice)
    return out


def _cap_only_blocks(rounds: int) -> List[Dict[str, Any]]:
    """The cap was hit and the forced summary produced nothing usable."""
    return [
        {
            "type": "narrative",
            "content": (
                f"I wasn't able to answer that within {rounds} rounds of data lookups. "
                "That usually means a tool kept failing or the question needs more steps "
                "than the limit allows — no partial answer is shown because none was "
                "produced. Try asking a narrower version of it."
            ),
        },
        {"type": "follow_ups", "suggestions": ["Ask about a single species", "Ask about one region"]},
    ]


def _looks_like_final_json(name: str, arguments: str) -> bool:
    """
    Some models occasionally wrap their mandated-JSON final answer in an
    undeclared "tool call" (commonly named "JSON") instead of returning it as
    plain content. Detect that pattern so it can be treated as the final
    answer directly, since Groq's API otherwise rejects the conversation on
    the next turn — a tool_call whose name isn't in the declared `tools` list
    can't be replayed back.
    """
    if name in TOOL_FUNCTIONS:
        return False
    try:
        data = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and "blocks" in data


async def execute_tool_call(call: Any) -> tuple[dict, dict]:
    """Run one tool call. Returns (plain args, result dict)."""
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        logger.error(f"Malformed tool call arguments for {name}: {call.function.arguments!r}")
        args = {}
    logger.info(f"Executing tool {name} with args: {args}")

    if name not in TOOL_FUNCTIONS:
        return args, {"error": f"Unknown tool: {name}"}

    try:
        result = await TOOL_FUNCTIONS[name](**args)
    except Exception as e:
        logger.error(f"Error executing {name}: {e}")
        return args, {"error": str(e)}

    if not isinstance(result, dict):
        result = {"result": result}
    return args, result


async def _execute_agent_loop(
    session: ResearchSession,
    system_prompt: str,
    user_message: str,
    meter: Optional[TurnMeter] = None,
) -> tuple[str, List[ToolCallRecord], List[dict], bool]:
    """
    Drive the model through tool calls until it produces a final text response.

    Returns the final text, the tool calls made this turn, the full message list
    the API ended up with (compressed-summary preamble included), and whether the
    round cap was hit.

    `meter` is optional observation only; when present it records what each
    round cost. It never affects control flow.
    """
    max_rounds = getattr(settings, "agent_max_tool_rounds", 5)
    model_name = AGENT_MODEL
    temperature = getattr(settings, "agent_temperature", 0.3)

    history = build_history(session)
    # Session context sits here, immediately before the question it disambiguates,
    # rather than at the front of the system message. Groq's prompt cache matches
    # on a prefix, so per-turn text at the front invalidated the whole prefix —
    # tool schemas included — on every single turn.
    context_message = build_context_message(session)
    messages: List[dict] = (
        [{"role": "system", "content": system_prompt}]
        + history
        + ([context_message] if context_message else [])
        + [{"role": "user", "content": user_message}]
    )

    # Tells the meter which message is this turn's question, so input tokens can
    # be attributed per stage. `agent_tools` is passed rather than imported there
    # so the schema cost is measured from the exact payload sent.
    if meter:
        meter.set_layout(
            user_index=len(messages) - 1,
            tool_schemas=agent_tools,
        )

    tool_calls: List[ToolCallRecord] = []
    round_count = 0
    cap_hit = False

    while True:
        try:
            if meter:
                meter.start_round()
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=agent_tools,
                tool_choice="auto",
                temperature=temperature,
            )
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise RuntimeError("tools" if round_count else "model") from e

        message = response.choices[0].message
        calls = message.tool_calls or []

        # Recorded before anything is appended, so the payload measured is the
        # one that was actually sent.
        if meter:
            meter.record_call(
                response,
                messages,
                tools_sent=True,
                tool_calls=[c.function.name for c in calls],
            )

        if not calls:
            messages.append(_assistant_message_dict(message))
            final_text = message.content or ""
            break

        if len(calls) == 1 and _looks_like_final_json(calls[0].function.name, calls[0].function.arguments):
            # Don't append this message to history — it isn't a real tool call
            # and would fail validation on a later turn.
            final_text = calls[0].function.arguments
            break

        if round_count >= max_rounds:
            # Don't append this message: it has unanswered tool_calls, and the API
            # requires every tool_call to be answered before the next turn. Force a
            # text-only reply from the state before this round instead. Omitting
            # `tools` entirely (rather than relying on tool_choice="none") is what
            # actually stops some models from emitting a tool call anyway.
            logger.warning(
                f"Session {session.session_id} hit max tool rounds ({max_rounds}). Forcing summary."
            )
            cap_hit = True
            try:
                if meter:
                    meter.start_round()
                forced = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                )
                # tools_sent=False: differencing this round's prompt against a
                # tools_sent=True round on the same turn measures the tool
                # schema cost directly, with no estimation.
                if meter:
                    meter.record_call(forced, messages, tools_sent=False)
                final_message = forced.choices[0].message
                messages.append(_assistant_message_dict(final_message))
                final_text = final_message.content or ""
            except Exception as e:
                logger.error(f"Groq API error on force summary: {e}")
                final_text = ""
            break

        round_count += 1
        messages.append(_assistant_message_dict(message))
        for call in calls:
            tool_t0 = time.perf_counter()
            args, result = await execute_tool_call(call)
            tool_ms = int((time.perf_counter() - tool_t0) * 1000)
            tool_calls.append(ToolCallRecord(name=call.function.name, args=args, result=result))
            if meter:
                meter.record_tool_result(call.function.name, result, latency_ms=tool_ms)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": json.dumps(result),
                }
            )

    return final_text, tool_calls, messages, cap_hit


def _turn_history(session: ResearchSession, messages: List[dict]) -> List[dict]:
    """
    Strip the system message and the synthetic compressed-summary exchange back
    off the message list, so only real turns are stored. The system message and
    summary are rebuilt fresh on the next turn.
    """
    # Drop every system message: the leading cached head, and the per-turn
    # session context injected before the user's question. Both are rebuilt from
    # live state next turn; persisting them would freeze stale context into
    # history and break the cacheable prefix.
    history = [m for m in messages if m.get("role") != "system"]
    if session.compressed_history:
        history = history[2:]  # drop the two synthetic summary messages
    return history


async def run_agent_turn(
    user_message: str,
    session_id: str,
    label: Optional[str] = None,
) -> AgentTurnResult:
    """
    Run one full agent turn against the session's memory: build the contextual
    prompt, call the model, then fold what happened back into session state.

    `label` is recorded alongside the token metrics only (the replay harness
    tags scenarios with it) and has no effect on the turn.
    """
    session, expired = get_session(session_id)

    coverage = await get_coverage_summary()
    system_prompt = build_system_prompt(session, coverage)

    meter = TurnMeter(
        session_id=session.session_id,
        model=AGENT_MODEL,
        user_message=user_message,
        label=label,
    )
    # Coverage is the stable tail of the cached head; measuring it apart from
    # the static contract shows how much of the prefix is actually fixed.
    meter.set_layout(coverage=coverage)

    turn_error: Optional[str] = None
    try:
        final_text, tool_calls, messages, cap_hit = await _execute_agent_loop(
            session, system_prompt, user_message, meter
        )
    except RuntimeError as e:
        # The model failed. Leave the session untouched rather than recording a
        # turn that never happened.
        turn_error = str(e)
        return AgentTurnResult(
            blocks=_error_blocks(str(e)),
            session_state=session.state_summary(),
            session_expired=expired,
            request_id=meter.request_id,
        )
    finally:
        # Emitted on every path, including a failed turn, so a turn that burned
        # tokens and then errored still reports what it cost.
        meter.emit(error=turn_error)

    if not final_text.strip():
        logger.error(f"Session {session_id}: model returned no final text.")
        # If the round cap is why we are here, say that rather than showing a
        # generic failure: the user should always learn that the work was cut
        # short, never just that something went wrong.
        blocks = (
            _cap_only_blocks(settings.agent_max_tool_rounds)
            if cap_hit
            else _error_blocks("model")
        )
        return AgentTurnResult(
            blocks=blocks,
            session_state=session.state_summary(),
            session_expired=expired,
            request_id=meter.request_id,
        )

    blocks = parse_agent_response(final_text)
    if cap_hit:
        blocks = _with_cap_notice(blocks, settings.agent_max_tool_rounds)

    turn_data = TurnData(
        user_message=user_message,
        tool_calls=tool_calls,
        final_blocks=blocks,
    )

    update_session_state(session, turn_data)
    session.raw_history = _turn_history(session, messages)
    maybe_compress_history(session)

    logger.info(
        f"Session {session_id} turn {session.turn_count}: "
        f"species={session.active_species}, regions={session.active_regions}, "
        f"raw_messages={len(session.raw_history)}, "
        f"compressed_chars={len(session.compressed_history)}"
    )

    return AgentTurnResult(
        blocks=blocks,
        session_state=session.state_summary(),
        session_expired=expired,
        request_id=meter.request_id,
    )


async def run_agent(user_message: str, session_id: str) -> List[Dict[str, Any]]:
    """Backwards-compatible wrapper returning just the blocks."""
    return (await run_agent_turn(user_message, session_id)).blocks


def reset_agent_session(session_id: str) -> bool:
    return delete_session(session_id)
