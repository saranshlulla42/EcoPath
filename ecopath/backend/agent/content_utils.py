"""
Small helpers for the agent's conversation messages.

`session.raw_history` holds plain OpenAI/Groq-style message dicts
(`{"role": ..., "content": ...}`, optionally with `tool_calls`), since the Groq
API is stateless and takes/returns plain JSON — no SDK objects to normalize.
"""

# Messages we inject into the conversation ourselves. They wear the user role so
# that turn-boundary detection can't mistake them for the start of a real turn.
SYNTHETIC_USER_PREFIXES = ("[PRIOR CONVERSATION SUMMARY",)


def extract_text(message: dict) -> str:
    """The text content of one message, or "" if it has none (e.g. a tool call)."""
    return (message.get("content") or "").strip()


def is_turn_start(message: dict) -> bool:
    """
    True when this message begins a new conversation turn — i.e. it is a user
    message carrying real text rather than a tool result.
    """
    if message.get("role") != "user":
        return False
    text = extract_text(message)
    if not text:
        return False
    return not text.startswith(SYNTHETIC_USER_PREFIXES)
