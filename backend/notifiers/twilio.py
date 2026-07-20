"""Twilio notifier — outbound voice call, env-guarded.

This is the only paid/free-trial tier. It is only enabled when TWILIO_SID,
TWILIO_TOKEN, and TWILIO_FROM are all set in the environment. Otherwise
**it runs in dry-run mode**: it logs the call it would have made and returns
SendResult(success=False, detail="dry-run: TWILIO_* not set").

When enabled, for each opted-in contact it places a real voice call that
reads a TTS message to the callee using the TwiML <Say> verb:

  "Hello. This is AeroGraph, the safety system for {user_name}. We have not
   received a response from them in the last 30 seconds and a possible fall
   was detected at {location_name}. Please try to reach them. To stop
   further calls, press 1."

The call uses Twilio's voice API (no pre-recorded audio file upload).

Tunisia note: Twilio does not currently support outbound voice calls to
Tunisian numbers (last checked). Even with creds set, calling a +216 number
will fail. The notifier records the failure and lets the other notifiers
(Telegram, WhatsApp) carry the alert.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import TWILIO_FROM, TWILIO_SID, TWILIO_TOKEN
from backend.notifiers.base import (
    AlertPayload, Contact, SendResult, filter_contacts_for_channel,
)

logger = logging.getLogger("aerograph.notifier.twilio")


# Lazy Twilio client — only imported on first use, so users without the
# twilio package installed (which is the default) still boot cleanly.
_client: Any = None


def _get_client():
    """Lazy-init the Twilio client. Returns None if env unset or import failed."""
    global _client
    if _client is not None:
        return _client
    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        return None
    try:
        from twilio.rest import Client
        _client = Client(TWILIO_SID, TWILIO_TOKEN)
    except Exception:
        logger.exception("TwilioNotifier: twilio.rest import failed")
        return None
    return _client


class TwilioNotifier:
    name = "twilio"

    async def send(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> list[SendResult]:
        targets = filter_contacts_for_channel(contacts, "call")

        # Dry-run when not configured or Twilio lib missing.
        if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
            logger.warning(
                "TwilioNotifier: dry-run (TWILIO_* not set). Would have called "
                "%d contact(s) with payload %s",
                len(targets), payload.incident_id,
            )
            return [
                SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False,
                    detail="dry-run: TWILIO_* env not set",
                )
                for c in targets
            ]

        client = _get_client()
        if client is None:
            return [
                SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False,
                    detail="twilio package not installed",
                )
                for c in targets
            ]

        results: list[SendResult] = []
        for c in targets:
            if not c.phone:
                results.append(SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False, detail="contact has no phone number",
                ))
                continue
            try:
                twiml = self._build_twiml(payload)
                # twilio.rest.Client.calls.create is *sync* — wrap in to_thread.
                import asyncio
                call = await asyncio.to_thread(
                    client.calls.create,
                    to=c.phone,
                    from_=TWILIO_FROM,
                    twiml=twiml,
                    timeout=20,
                )
                results.append(SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=bool(call.sid),
                    detail=f"call_sid={call.sid}" if call.sid else "no sid returned",
                ))
            except Exception as e:
                logger.warning("TwilioNotifier: call failed for %s: %s", c.id, e)
                results.append(SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False,
                    detail=f"exception: {type(e).__name__}: {e}",
                ))
        return results

    @staticmethod
    def _build_twiml(payload: AlertPayload) -> str:
        """TwiML using <Say> for the spoken message."""
        user = payload.user_name or "the user"
        loc = payload.location_name or "an unknown location"
        msg = (
            f"Hello. This is AeroGraph, the safety system for {user}. "
            f"We have not received a response from them in the last 30 seconds "
            f"and a possible fall was detected at {loc}. "
            f"Please try to reach them. To stop further calls, press 1."
        )
        # Escape XML-special chars so the TwiML stays well-formed.
        msg = (msg.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
              f'<Say voice="Polly.Joanna">{msg}</Say>'
              '<Gather numDigits="1" action="/v1/safety/twilio_gather" method="POST">'
                '<Say>If you have reached this person, press 1 now.</Say>'
              '</Gather>'
              '<Say>We will try again later. Goodbye.</Say>'
            '</Response>'
        )
