"""WhatsApp notifier — secondary, free, works in Tunisia.

Calls the local Baileys bridge at WHATSAPP_BRIDGE_URL (default
http://127.0.0.1:7878). The bridge is a small Node.js subproject
(``notifier-whatsapp/``) that uses the open-source Baileys library to send
messages via the WhatsApp Web protocol. Bridge contract:

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
        results: list[SendResult] = []
        for c in targets:
            if not c.phone:
                results.append(SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False, detail="contact has no phone number",
                ))
                continue
            res = await self._send_one(c, payload)
            results.append(res)
        return results

    async def _send_one(
        self, contact: Contact, payload: AlertPayload,
    ) -> SendResult:
        body = {
            "phone": contact.phone,
            "text": payload.summary_text(),
            "images_base64": [
                base64.b64encode(jpeg).decode("ascii")
                for jpeg in payload.keyframes_jpeg[:3]
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{WHATSAPP_BRIDGE_URL}/send",
                    json=body,
                )
            ok = r.status_code == 200 and r.json().get("ok", False)
            detail = r.json().get("detail", f"status={r.status_code}") if r.status_code == 200 else f"status={r.status_code}"
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
