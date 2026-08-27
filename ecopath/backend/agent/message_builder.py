"""
Assembles the conversation history handed to the chat model for a turn:
compressed summary of old turns, then the raw recent turns. The system message
and the current user message are not included here — the caller adds those.
"""

import logging

from agent.session import ResearchSession

logger = logging.getLogger("ecopath.agent.message_builder")

COMPRESSED_PREFIX = (
    "[PRIOR CONVERSATION SUMMARY — This summarizes earlier parts of this research "
    "session. Use it for context. Do not respond to it directly.]\n\n"
)

COMPRESSED_ACK = (
    "I have the context from our earlier conversation. I'll use it to inform my responses."
)


def build_history(session: ResearchSession) -> list[dict]:
    """
    The prior-turns portion of the `messages` array sent to the model. The current
    user message is *not* included — the caller appends it separately.

    The compressed summary is injected as a synthetic user/assistant exchange at
    the head of the history, so it reads as background the model already
    acknowledged rather than something to respond to.
    """
    history: list[dict] = []

    if session.compressed_history:
        history.append({"role": "user", "content": COMPRESSED_PREFIX + session.compressed_history})
        history.append({"role": "assistant", "content": COMPRESSED_ACK})

    history.extend(session.raw_history)
    return history


def build_messages(session: ResearchSession, current_user_message: str) -> list[dict]:
    """Full message array including the current turn. Useful for logging/inspection."""
    return build_history(session) + [{"role": "user", "content": current_user_message}]
