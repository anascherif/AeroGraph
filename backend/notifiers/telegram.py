"""Telegram notifier — primary, free, no Tunisia restriction.

Uses python-telegram-bot to send a text message + 3 keyframe photos (sendMediaGroup)
+ a synthesized voice note (sendVoice, via TTS) to each contact opted into Telegram.

Auth: TELEGRAM_BOT_TOKEN env var. Created once via @BotFather (5 minutes, free).
Each contact's chat target is resolved (in priority order) from:
  1. contact.telegram_user_id (numeric chat id, e.g. "123456789")
  2. contact.telegram_username (e.g. "@mom" — requires the contact to have
     started a conversation with the bot first; the bot cannot initiate
     DMs with arbitrary usernames.)

If neither is set we skip the contact silently and record a SendResult
explaining that no Telegram route exists for them.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from typing import Any

from backend.config import TELEGRAM_BOT_TOKEN
from backend.notifiers.base import (
    AlertPayload, Contact, SendResult, filter_contacts_for_channel,
)

logger = logging.getLogger("aerograph.notifier.telegram")


# Lazy bot singleton — initialised on first use with double-checked locking
# via _bot_lock (asyncio.Lock created at import time, which is safe on Py3.10+
# because asyncio.Lock() no longer needs a running loop to be constructed).
_bot: Any = None
_bot_lock: asyncio.Lock | None = None


def _ensure_lock() -> asyncio.Lock:
    """Create _bot_lock lazily, so we never bind it to a closed/missing loop.

    asyncio.Lock on Python 3.10+ can be created without a running loop and
    will adopt the loop it's first used in. We still create it on demand to
    avoid any chance of binding to a transient event loop at import time.
    """
    global _bot_lock
    if _bot_lock is None:
        _bot_lock = asyncio.Lock()
    return _bot_lock


async def _get_bot() -> Any:
    """Lazily initialize the Telegram Bot client. Returns None if no token.

    Two concurrent calls (e.g. escalate fires while a manual /test_alert is
    in flight on a second asyncio task) could both pass the fast-path check
    and both import+create the Bot. _bot_lock serialises the slow path;
    inside the lock we re-check _bot to avoid double-initialisation.
    """
    global _bot
    if _bot is not None:
        return _bot
    if not TELEGRAM_BOT_TOKEN:
        return None
    lock = _ensure_lock()
    async with lock:
        # Double-check inside the lock — another task might have initialised
        # while we were waiting.
        if _bot is not None:
            return _bot
        try:
            from telegram import Bot
            _bot = Bot(token=TELEGRAM_BOT_TOKEN)
        except Exception:
            logger.exception("TelegramNotifier: failed to init Bot from token")
            return None
        return _bot


class TelegramNotifier:
    name = "telegram"

    async def send(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> list[SendResult]:
        bot = await _get_bot()
        if bot is None:
            # No token configured — return a single failed result per contact.
            return [
                SendResult(
                    notifier=self.name,
                    contact_id=c.id,
                    success=False,
                    detail="TELEGRAM_BOT_TOKEN not set",
                )
                for c in filter_contacts_for_channel(contacts, "telegram")
            ]

        targets = filter_contacts_for_channel(contacts, "telegram")
        # Parallelise per-contact sends — Telegram API can happily handle
        # concurrent requests and the escalator climbs out of the 60s+
        # blocked window when sending to multiple family members sequentially.
        return await asyncio.gather(
            *(self._send_one(bot, c, payload) for c in targets)
        )

    async def _send_one(
        self, bot: Any, contact: Contact, payload: AlertPayload,
    ) -> SendResult:
        chat_id = self._resolve_chat_id(contact)
        if chat_id is None:
            return SendResult(
                notifier=self.name,
                contact_id=contact.id,
                success=False,
                detail="contact has neither telegram_user_id nor telegram_username",
            )

        # Pre-render the voice BEFORE the await chain so the cleanup scope
        # is unambiguous (see comment in finally block below).
        voice_path: str | None = None
        try:
            # 1. Text alert.
            text_msg = payload.summary_text()
            await bot.send_message(chat_id=chat_id, text=text_msg)

            # 2. Keyframe photo carousel (up to 3).
            kfs = payload.keyframes_jpeg[:3]
            if kfs:
                # python-telegram-bot InputMediaPhoto accepts BytesIO.
                media = [
                    _bytes_io(jpeg, f"frame_{i}.jpg")
                    for i, jpeg in enumerate(kfs)
                ]
                try:
                    from telegram import InputMediaPhoto
                    group = [
                        InputMediaPhoto(media=m, caption="AeroGraph: recent frames")
                        for m in media
                    ]
                    await bot.send_media_group(chat_id=chat_id, media=group)
                except Exception as e:
                    # Fallback: send only the first photo. python-telegram-bot
                    # consumed the BytesIO buffers above during the failed
                    # send_media_group call (cursor advanced past EOF), so
                    # we MUST rebuild a fresh BytesIO from the raw bytes —
                    # reusing media[0] would send a 0-byte image.
                    logger.warning(
                        "Telegram: send_media_group failed (%s) — sending first only",
                        e,
                    )
                    await bot.send_photo(chat_id=chat_id, photo=_bytes_io(kfs[0]))

            # 3. Synthesized voice note. Render via pyttsx3 to a temp file,
            # then upload it. Render happens off the event loop via to_thread.
            voice_path = await asyncio.to_thread(self._render_voice, text_msg)
            if voice_path:
                with open(voice_path, "rb") as f:
                    await bot.send_voice(chat_id=chat_id, voice=f)

            return SendResult(
                notifier=self.name,
                contact_id=contact.id,
                success=True,
                detail=f"sent to chat_id={chat_id}",
            )
        except Exception as e:
            logger.exception("TelegramNotifier: send failed for %s", contact.id)
            return SendResult(
                notifier=self.name,
                contact_id=contact.id,
                success=False,
                detail=f"exception: {type(e).__name__}: {e}",
            )
        finally:
            # voice_path is initialised to None at the top of the function,
            # so even if _render_voice raises before the assignment the
            # finally block has a defined reference rather than NameError.
            if voice_path is not None:
                try:
                    os.remove(voice_path)
                except Exception:
                    pass

    @staticmethod
    def _resolve_chat_id(contact: Contact) -> str | None:
        if contact.telegram_user_id:
            return contact.telegram_user_id
        if contact.telegram_username:
            # The username must include @ — the bot API accepts either form.
            u = contact.telegram_username
            return u if u.startswith("@") else f"@{u}"
        return None

    @staticmethod
    def _render_voice(text: str) -> str | None:
        """Render TTS to a temp .wav file. Returns the path or None."""
        try:
            from backend.pipeline.tts_engine import save_to_file
        except Exception:
            logger.exception("TelegramNotifier: tts_engine import failed")
            return None
        try:
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            save_to_file(text, path)
            return path
        except Exception:
            logger.exception("TelegramNotifier: save_to_file failed")
            return None


def _bytes_io(data: bytes, name: str | None = None) -> io.BytesIO:
    """Wrap raw bytes in a fresh BytesIO stream.

    Centralising this so we never fall into the bug where a BytesIO is passed
    to two different API calls — the cursor is advanced by the first reader
    and the second receives an EOF stream.
    """
    buf = io.BytesIO(data)
    if name:
        buf.name = name
    return buf
