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
import tempfile
from typing import Any

from backend.config import TELEGRAM_BOT_TOKEN
from backend.notifiers.base import (
    AlertPayload, Contact, SendResult, filter_contacts_for_channel,
)

logger = logging.getLogger("aerograph.notifier.telegram")

# Lazy import so the rest of the system can boot even if telegram isn't
# installed/configured.
_bot: Any = None
_bot_lock = asyncio.Lock()


async def _get_bot():
    """Lazily initialize the Telegram Bot client. Returns None if no token."""
    global _bot
    if _bot is not None:
        return _bot
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        # python-telegram-bot >= 20
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

        results: list[SendResult] = []
        targets = filter_contacts_for_channel(contacts, "telegram")
        for c in targets:
            res = await self._send_one(bot, c, payload)
            results.append(res)
        return results

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

        try:
            # 1. Text alert.
            text_msg = payload.summary_text()
            await bot.send_message(chat_id=chat_id, text=text_msg)

            # 2. Keyframe photo carousel (up to 3).
            kfs = payload.keyframes_jpeg[:3]
            if kfs:
                # python-telegram-bot InputMediaPhoto accepts BytesIO
                media = []
                for i, jpeg in enumerate(kfs):
                    buf = io.BytesIO(jpeg)
                    buf.name = f"frame_{i}.jpg"
                    media.append(buf)
                # sendPhoto can only send one; use send_media_group for many.
                # python-telegram-bot media param accepts BufferedIOBase.
                from telegram import InputMediaPhoto
                group = [InputMediaPhoto(media=m, caption="AeroGraph: recent frames") for m in media]
                try:
                    await bot.send_media_group(chat_id=chat_id, media=group)
                except Exception as e:
                    # Some bots / older servers — fall back to first photo only.
                    logger.warning("Telegram: send_media_group failed (%s) — sending first only", e)
                    if media:
                        await bot.send_photo(chat_id=chat_id, photo=media[0])

            # 3. Synthesized voice note. We render via pyttsx3 (already used
            # elsewhere) to a temp file, then upload it.
            try:
                voice_path = await asyncio.to_thread(self._render_voice, text_msg)
                if voice_path:
                    with open(voice_path, "rb") as f:
                        await bot.send_voice(chat_id=chat_id, voice=f)
            finally:
                if voice_path:
                    try:
                        import os as _os
                        _os.remove(voice_path)
                    except Exception:
                        pass

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
            import tempfile, os
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            save_to_file(text, path)
            return path
        except Exception:
            logger.exception("TelegramNotifier: save_to_file failed")
            return None
