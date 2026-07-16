"""Speech-to-text for AeroGraph.

Primary: Groq cloud Whisper (fast, free tier).
Fallback: local faster-whisper (works offline but slower on CPU).
"""

from __future__ import annotations

import io
import logging
from typing import Optional

from backend.config import GROQ_API_KEY, GROQ_STT_MODEL

logger = logging.getLogger("aerograph.stt")

# Lazy-loaded singletons
_groq_client = None
_local_model = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not set — cannot use Groq STT.")
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        _local_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _local_model


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    mime_type: str = "audio/webm",
    language: str = "en",
) -> str:
    """Transcribe raw audio bytes.  Tries Groq first, falls back to local."""
    # --- Try Groq cloud ---
    try:
        client = _get_groq_client()
        # Groq expects a file-like object
        buf = io.BytesIO(audio_bytes)
        ext = mime_type.split("/")[-1]
        if ext in ("x-wav", "wav"):
            ext = "wav"
        buf.name = f"audio.{ext}"
        resp = client.audio.transcriptions.create(
            model=GROQ_STT_MODEL,
            file=buf,
            language=language,
        )
        text = (resp.text or "").strip()
        if text:
            logger.info("Groq STT: '%s'", text)
            return text
    except Exception:
        logger.warning("Groq STT failed, falling back to local model.", exc_info=True)

    # --- Fallback: local faster-whisper ---
    try:
        model = _get_local_model()
        # Write bytes to a temp buffer
        buf = io.BytesIO(audio_bytes)
        segments, info = model.transcribe(buf, language=language)
        text = " ".join(seg.text.strip() for seg in segments)
        logger.info("Local STT: '%s'", text)
        return text
    except Exception:
        logger.exception("Local STT also failed.")
        return ""


def transcribe_file(path: str, *, language: str = "en") -> str:
    """Transcribe an audio file on disk."""
    with open(path, "rb") as f:
        return transcribe_audio_bytes(f.read(), language=language)
