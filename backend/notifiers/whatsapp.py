"""WhatsApp notifier — secondary, free, works in Tunisia.

Calls the local whatsapp-web.js bridge at WHATSAPP_BRIDGE_URL (default
http://127.0.0.1:7878). The bridge is a small Node.js subproject
(``notifier-whatsapp/``) that drives a real headless Chromium via
whatsapp-web.js — looks like genuine WhatsApp Web traffic to the server.
Bridge contract:

  POST /send
    body: {
      "phone": "<full-international-number>",
      "text":  "<alert summary>",
      "images_base64": ["<base64-jpeg>", ...]   # optional, max 3, sent as
                                                # consecutive WhatsApp images
    }
    response: { "ok": bool, "detail": string }

The Python side never imports Baileys; we just do an HTTP POST with a short
timeout. If the bridge is down or unreachable, we return SendResult(success=False).
That failure does NOT abort the other notifiers — the NotifierBus runs them
in parallel with return_exceptions=True.

Env guard: WHATSAPP_BRIDGE_URL may be left at its default; we always try it
but a 5s connect timeout means an unreachable bridge fails fast and cleanly
without holding up the alert.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

import httpx

from backend.config import WHATSAPP_BRIDGE_URL
from backend.notifiers.base import (
    AlertPayload, Contact, SendResult, filter_contacts_for_channel,
)

logger = logging.getLogger("aerograph.notifier.whatsapp")


class WhatsAppNotifier:
    name = "whatsapp"

    async def send(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> list[SendResult]:
        targets = filter_contacts_for_channel(contacts, "whatsapp")
        # Parallelise per-contact sends — escalations to multiple contacts
        # otherwise block sequentially on the bridge timeout (10s each),
        # which can push alert delivery past 60s for N=3 contacts.
        return await asyncio.gather(
            *(self._send_one(c, payload) for c in targets)
        )

    async def _send_one(
        self, contact: Contact, payload: AlertPayload,
    ) -> SendResult:
        if not contact.phone:
            return SendResult(
                notifier=self.name, contact_id=contact.id,
                success=False, detail="contact has no phone number",
            )
        body = {
            "phone": "".join(c for c in contact.phone if c.isdigit()),
            "text": payload.summary_text(),
            "images_base64": [
                base64.b64encode(jpeg).decode("ascii")
                for jpeg in payload.keyframes_jpeg[:3]
            ],
        }
        # MINOR #29: pre-validate that the body round-trips through JSON with
        # ensure_ascii=True so Arabic names ("محمد") don't silently get mangled
        # into "??" or split surrogate pairs downstream. This is a no-op for
        # ASCII content but catches UTF-8 issues at the notifier boundary
        # instead of letting them surface as mojibake in the WhatsApp chat.
        try:
            json.dumps(body, ensure_ascii=True)
        except (TypeError, ValueError) as e:
            logger.warning(
                "WhatsAppNotifier: payload is not JSON-serialisable "
                "for %s: %s", contact.id, e,
            )
            return SendResult(
                notifier=self.name, contact_id=contact.id,
                success=False,
                detail=f"payload not JSON-serialisable: {e}",
            )
        try:
            # 5s connect + 10s read — matches the docstring claim that an
            # unreachable bridge fails fast rather than blocking the alert
            # for the full 10s.
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=1.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{WHATSAPP_BRIDGE_URL}/send",
                    json=body,
                )
            # Parse the body once — calling r.json() twice hits an httpx cache
            # that is fragile across versions.
            try:
                data = r.json()
            except Exception:
                data = {}
            ok = r.status_code == 200 and bool(data.get("ok", False))
            detail = (
                data.get("detail", f"status={r.status_code}")
                if r.status_code == 200
                else f"status={r.status_code}"
            )
            return SendResult(
                notifier=self.name, contact_id=contact.id,
                success=ok, detail=detail,
            )
        except Exception as e:
            logger.warning("WhatsAppNotifier: send failed for %s: %s", contact.id, e)
            return SendResult(
                notifier=self.name, contact_id=contact.id,
                success=False,
                detail=f"bridge unreachable or error: {type(e).__name__}: {e}",
            )
