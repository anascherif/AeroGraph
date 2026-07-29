"""Text-to-speech for AeroGraph.

Uses Windows SAPI5 directly via comtypes (pyttsx3's setProperty('voice') is
a no-op on recent pyttsx3 + Windows builds because of a known comtypes
BSTR-comparison bug). We therefore go one layer below pyttsx3 and drive
ISpeechVoice ourselves.

Public API (unchanged for callers):
  speak(text)            block until finished
  speak_async(text)      fire-and-forget background thread
  save_to_file(text, p)  render to .wav (used by Telegram notifier)
  speak_stream(texts)    batched streamed playback

Voice selection: Windows SAPI5 defaults to whatever the OS picked first
(often French on French-localized installs), which makes the hackathon
demo speak English in a French accent. We auto-detect the first English
voice available and pin to it. Override via the TTS_VOICE_ID config
constant (env: AEROGRAPH_TTS_VOICE_ID).

COM threading: every worker thread that touches SAPI must call
comtypes.CoInitialize() BEFORE its first COM call. We do that in the
public speak/save functions whenever the calling thread differs from the
main thread, so speak_async() works without the caller needing to know.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import comtypes
import comtypes.client

from backend.config import TTS_VOICE_ID

logger = logging.getLogger("aerograph.tts")

_voice = None         # ISpeechVoice COM object
_voices_cache = None  # ISpeechObjectTokens collection (cached after init)
_lock = threading.Lock()
_main_thread_id = threading.get_ident()


# Voice-name hints we treat as English. Used as a fallback when the SAPI5
# `languages` attribute is empty (which happens on some Windows installs).
_ENGLISH_NAME_HINTS = (
    "english", "zira", "aria", "david", "eva mobile", "mark mobile",
)


def _voice_description(token) -> str:
    """Get the human-readable description of an ISpeechObjectToken."""
    try:
        return token.GetDescription() or ""
    except Exception:
        return ""


def _is_english_voice(token) -> bool:
    """True if the SAPI5 voice's description matches English."""
    desc = _voice_description(token).lower()
    return any(hint in desc for hint in _ENGLISH_NAME_HINTS)


def _pick_english_voice_token(voices) -> object | None:
    """Return the first English voice token, or None."""
    for i in range(voices.Count):
        token = voices.Item(i)
        if _is_english_voice(token):
            return token
    return None


def _find_voice_by_id(voices, voice_id: str) -> object | None:
    """Return the voice token whose description matches voice_id, or None."""
    for i in range(voices.Count):
        token = voices.Item(i)
        if voice_id in _voice_description(token):
            return token
    return None


def _ensure_com_initialised() -> None:
    """COM-initialize the current thread if it hasn't been yet.

    Each OS thread that uses COM apartment-threaded objects must call
    CoInitialize() before its first COM call, otherwise
    CoCreateInstance raises OSError -2147221008 ('CoInitialize has not
    been called'). The main thread is initialised by comtypes
    implicitly; worker threads from speak_async() need this.
    """
    if threading.get_ident() == _main_thread_id:
        return
    try:
        # COINIT_MULTITHREADED == 0x0; COINIT_APARTMENTTHREADED == 0x2.
        # SAPI works with either; apartment is the SAPI default.
        comtypes.CoInitialize()
    except OSError:
        # Already initialised in this thread -> ignore.
        pass


def _get_voice():
    """Return the (cached) English SAPI5 voice, or fall back to system default."""
    global _voice, _voices_cache
    if _voice is None:
        _ensure_com_initialised()
        _voice = comtypes.client.CreateObject("SAPI.SpVoice")
        _voices_cache = _voice.GetVoices()

        target = None
        if TTS_VOICE_ID.strip():
            target = _find_voice_by_id(_voices_cache, TTS_VOICE_ID.strip())
        if target is None:
            target = _pick_english_voice_token(_voices_cache)

        if target is not None:
            _voice.Voice = target
            try:
                _voice.Rate = 1  # slight speed-up from default 0
            except Exception:
                pass
            logger.info(
                "TTS: pinned voice to %s",
                _voice_description(target) or "<unknown>",
            )
        else:
            logger.warning(
                "TTS: no English voice found; falling back to system default. "
                "Set AEROGRAPH_TTS_VOICE_ID in .env to force one."
            )
    return _voice


def speak(text: str) -> None:
    """Block until TTS finishes speaking the given text."""
    if not text.strip():
        return
    with _lock:
        voice = _get_voice()
        # Flags: 0 = default (sync). Speak() blocks until done on SAPI5.
        voice.Speak(text, 0)


def speak_async(text: str) -> None:
    """Fire-and-forget TTS in a background thread."""
    t = threading.Thread(target=speak, args=(text,), daemon=True)
    t.start()


def save_to_file(text: str, path: str | Path) -> None:
    """Render TTS to a 16 kHz mono .wav file (Telegram voice-note friendly)."""
    if not text.strip():
        return
    with _lock:
        voice = _get_voice()
        # ISpeechFileStream: mode 3 = SSFMCreateForFileOverwrite, format
        # type 22 = SAFT16kHz16BitMono (good for Telegram voice notes).
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        try:
            stream.Format.Type = 22
            stream.Open(str(path), 3, False)
            voice.AudioOutputStream = stream
            voice.Speak(text, 0)
        finally:
            # Restore default audio output (NULL stream == speaker) so
            # subsequent speak() calls don't accidentally try to write to
            # the file again.
            try:
                voice.AudioOutputStream = None
            except Exception:
                pass
            try:
                stream.Close()
            except Exception:
                pass


def speak_stream(texts: list[str]) -> None:
    """Speak a list of text chunks in order (e.g. streamed LLM tokens).

    Batches tokens into sentence-like chunks for more natural pacing.
    """
    buffer = ""
    sentence_end = set(".!?;:")

    for chunk in texts:
        buffer += chunk
        if buffer and buffer[-1] in sentence_end:
            speak(buffer)
            buffer = ""

    if buffer.strip():
        speak(buffer)
