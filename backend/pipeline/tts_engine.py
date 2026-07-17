"""Text-to-speech for AeroGraph.

Uses pyttsx3 (offline, cross-platform SAPI5 on Windows).
Provides both blocking ``speak()`` and a streaming ``speak_stream()``.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pyttsx3

logger = logging.getLogger("aerograph.tts")

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", 175)   # words per minute
        _engine.setProperty("volume", 1.0)
    return _engine


def speak(text: str) -> None:
    """Block until TTS finishes speaking the given text."""
    if not text.strip():
        return
    with _lock:
        engine = _get_engine()
        engine.say(text)
        engine.runAndWait()


def speak_async(text: str) -> None:
    """Fire-and-forget TTS in a background thread."""
    t = threading.Thread(target=speak, args=(text,), daemon=True)
    t.start()


def save_to_file(text: str, path: str | Path) -> None:
    """Render TTS to a .wav file."""
    if not text.strip():
        return
    with _lock:
        engine = _get_engine()
        engine.save_to_file(text, str(path))
        engine.runAndWait()


def speak_stream(texts: list[str]) -> None:
    """Speak a list of text chunks in order (e.g. streamed LLM tokens).

    Batches tokens into sentence-like chunks for more natural pacing.
    """
    buffer = ""
    sentence_end = set(".!?;:")

    for chunk in texts:
        buffer += chunk
        # If we hit a sentence boundary, flush
        if buffer and buffer[-1] in sentence_end:
            speak(buffer)
            buffer = ""

    # Flush remainder
    if buffer.strip():
        speak(buffer)
