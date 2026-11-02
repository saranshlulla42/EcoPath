"""
Ollama adapter — the local report model.

Concurrency is pinned to 1 in the registry: parallel generations on one GPU
thrash memory and end up slower than serialising them. Responses are never
cached, since the same prompt is expected to be re-generated.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from config import get_settings
from data.envelope import Result, failed, ok
from data.http import fetch

logger = logging.getLogger("ecopath.data.ollama")
settings = get_settings()


async def is_up() -> bool:
    """Whether the local Ollama HTTP endpoint is reachable."""
    res = await fetch("ollama", "health", "api/tags", ttl=0, use_cache=False)
    return res.ok


async def chat(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.4,
    num_predict: int = 2048,
    want_json: bool = False,
    output_schema: Optional[dict[str, Any]] = None,
    include_metadata: bool = False,
) -> Result:
    """One non-streaming chat completion. Returns the assistant text."""
    payload: dict[str, Any] = {
        "model": model or settings.ollama_report_model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "top_p": 0.9, "num_predict": num_predict},
    }
    if output_schema is not None:
        payload["format"] = output_schema
    elif want_json:
        payload["format"] = "json"

    res = await fetch("ollama", "chat", "api/chat", method="POST",
                      json_body=payload, use_cache=False)
    if not res.ok:
        return res

    data = res.data
    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, dict) and message.get("content"):
            if include_metadata:
                return ok({"content": message["content"], **{key: data.get(key) for key in (
                    "done_reason", "eval_count", "prompt_eval_count", "total_duration", "load_duration",
                    "prompt_eval_duration", "eval_duration",
                )}}, "ollama", "chat")
            return ok(message["content"], "ollama", "chat")
        if isinstance(data.get("response"), str) and data["response"]:
            return ok(data["response"], "ollama", "chat")

    return failed("ollama", "chat", "Ollama returned a malformed response")
