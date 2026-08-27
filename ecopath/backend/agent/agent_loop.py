import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from groq import AsyncGroq

from config import get_settings
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
from agent.system_prompt import build_system_prompt
from agent.tool_declarations import agent_tools
from agent.tools import (
    compare_species,
    correlate_weather,
    query_anomalies,
    query_migration,
    query_population,
)

logger = logging.getLogger("ecopath.agent.agent_loop")
settings = get_settings()

client = AsyncGroq(api_key=settings.groq_api_key)

# We map the function names to the actual python functions
TOOL_FUNCTIONS = {
    "query_population": query_population,
    "query_anomalies": query_anomalies,
    "query_migration": query_migration,
    "compare_species": compare_species,
    "correlate_weather": correlate_weather,
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
    session: ResearchSession, system_prompt: str, user_message: str
) -> tuple[str, List[ToolCallRecord], List[dict]]:
    """
    Drive the model through tool calls until it produces a final text response.

    Returns the final text, the tool calls made this turn, and the full message
    list the API ended up with (compressed-summary preamble included).
    """
    max_rounds = getattr(settings, "agent_max_tool_rounds", 5)
    model_name = getattr(settings, "agent_model", "llama-3.3-70b-versatile")
    temperature = getattr(settings, "agent_temperature", 0.3)

    messages: List[dict] = (
        [{"role": "system", "content": system_prompt}]
        + build_history(session)
        + [{"role": "user", "content": user_message}]
    )

    tool_calls: List[ToolCallRecord] = []
    round_count = 0

    while True:
        try:
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
            try:
                forced = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                )
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
            args, result = await execute_tool_call(call)
            tool_calls.append(ToolCallRecord(name=call.function.name, args=args, result=result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": json.dumps(result),
                }
            )

    return final_text, tool_calls, messages


def _turn_history(session: ResearchSession, messages: List[dict]) -> List[dict]:
    """
    Strip the system message and the synthetic compressed-summary exchange back
    off the message list, so only real turns are stored. The system message and
    summary are rebuilt fresh on the next turn.
    """
    history = messages[1:]  # drop the leading system message
    if session.compressed_history:
        history = history[2:]  # drop the two synthetic summary messages
    return history


async def run_agent_turn(user_message: str, session_id: str) -> AgentTurnResult:
    """
    Run one full agent turn against the session's memory: build the contextual
    prompt, call the model, then fold what happened back into session state.
    """
    session, expired = get_session(session_id)

    system_prompt = build_system_prompt(session)

    try:
        final_text, tool_calls, messages = await _execute_agent_loop(
            session, system_prompt, user_message
        )
    except RuntimeError as e:
        # The model failed. Leave the session untouched rather than recording a
        # turn that never happened.
        return AgentTurnResult(
            blocks=_error_blocks(str(e)),
            session_state=session.state_summary(),
            session_expired=expired,
        )

    if not final_text.strip():
        logger.error(f"Session {session_id}: model returned no final text.")
        return AgentTurnResult(
            blocks=_error_blocks("model"),
            session_state=session.state_summary(),
            session_expired=expired,
        )

    blocks = parse_agent_response(final_text)

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
    )


async def run_agent(user_message: str, session_id: str) -> List[Dict[str, Any]]:
    """Backwards-compatible wrapper returning just the blocks."""
    return (await run_agent_turn(user_message, session_id)).blocks


def reset_agent_session(session_id: str) -> bool:
    return delete_session(session_id)
