"""LLM client for AeroGraph.

Wraps the OpenAI-compatible NVIDIA NIM API.  Provides a thin helper that
injects a spatial-memory system prompt and streams / returns responses.
"""

from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from backend.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL

logger = logging.getLogger("aerograph.llm")

_SYSTEM_PROMPT = """\
You are AeroGraph, a voice assistant for visually impaired users.
You help them understand and navigate their surroundings by answering questions
about a spatial memory graph built from prior visits.

You receive:
- A spatial memory summary (objects, locations, change history).
- The user's question (transcribed from speech).

Rules:
- Answer in 1-3 short sentences.  Be direct and actionable.
- If describing changes, mention the object name, what changed, and direction.
- If the user asks about an object you don't have data for, say so clearly.
- Never guess positions.  Only report what the memory graph contains.
- Use natural, conversational tone — this will be read aloud via TTS.
"""

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY is not set — LLM queries will not work.")
        _client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)
    return _client


def ask(
    user_message: str,
    *,
    context: str = "",
    model: str = "",
    max_tokens: int = 256,
    temperature: float = 0.3,
) -> str:
    """Send a single-turn query and return the full response text.

    Parameters
    ----------
    user_message:
        The user's question (already transcribed from speech).
    context:
        Optional spatial-memory context block prepended to the user message.
    model:
        Override the default model from config.
    """
    client = _get_client()
    model = model or NVIDIA_MODEL

    content_parts: list[str] = []
    if context:
        content_parts.append(f"--- Spatial Memory Context ---\n{context}")
    content_parts.append(f"--- User Question ---\n{user_message}")
    content = "\n\n".join(content_parts)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (resp.choices[0].message.content or "").strip()
        logger.info("LLM response (%d tokens): %.100s", resp.usage.total_tokens, text)
        return text
    except Exception:
        logger.exception("LLM request failed")
        raise RuntimeError("LLM request failed. Please retry or check the service.")


def ask_stream(
    user_message: str,
    *,
    context: str = "",
    model: str = "",
    max_tokens: int = 256,
    temperature: float = 0.3,
):
    """Yield response chunks as they arrive (for streaming TTS)."""
    client = _get_client()
    model = model or NVIDIA_MODEL

    content_parts: list[str] = []
    if context:
        content_parts.append(f"--- Spatial Memory Context ---\n{context}")
    content_parts.append(f"--- User Question ---\n{user_message}")
    content = "\n\n".join(content_parts)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception:
        logger.exception("LLM stream failed")
        yield "Sorry, I couldn't process that right now."
