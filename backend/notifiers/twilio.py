"""Twilio notifier — outbound voice call, env-guarded.

This is the only paid/free-trial tier. It is only enabled when TWILIO_SID,
TWILIO_TOKEN, and TWILIO_FROM are all set in the environment. Otherwise
**it runs in dry-run mode**: it logs the call it would have made and returns
SendResult(success=True, detail="dry-run: TWILIO_* not set"). Dry-run is
intentionally reported as success=True so the dashboard doesn't show a
perpetual red "twilio failed" badge on every escalation in deployments that
never intend to use Twilio (the common case).

When enabled, for each opted-in contact it places a real voice call that
reads a TTS message to the callee using the TwiML <Say> verb. The call
simply announces the alert and hangs up — no <Gather> DTMF callback is
used because AeroGraph does not advertise a public HTTPS callback URL
(the hack runs locally).

Tunisia note: Twilio does not currently support outbound voice calls to
Tunisian numbers (last checked). Even with creds set, calling a +216 number
will fail. The notifier records the failure and lets the other notifiers
(Telegram, WhatsApp) carry the alert.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.config import TWILIO_FROM, TWILIO_SID, TWILIO_TOKEN
from backend.notifiers.base import (
    AlertPayload, Contact, SendResult, filter_contacts_for_channel,
)

logger = logging.getLogger("aerograph.notifier.twilio")


def _is_configured() -> bool:
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)


class TwilioNotifier:
    """Stateless outbound-voice notifier.

    Each ``send()`` call constructs a fresh :class:`twilio.rest.Client` per
    contact inside ``asyncio.to_thread`` because ``requests.Session`` (the
    HTTP transport the twilio client uses internally) is NOT thread-safe
    for concurrent use across threads. Sharing one client across contacts
    would corrupt the auth-header / cookie jar — so we don't.
    """

    name = "twilio"

    async def send(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> list[SendResult]:
        targets = filter_contacts_for_channel(contacts, "call")

        # Dry-run when not configured. Reported as success=True with a
        # descriptive detail so the dashboard's per-channel status doesn't
        # show perpetual red badges for a channel that was never opted-in.
        if not _is_configured():
            logger.warning(
                "TwilioNotifier: dry-run (TWILIO_* not set). Would have called "
                "%d contact(s) with payload %s",
                len(targets), payload.incident_id,
            )
            return [
                SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=True,
                    detail="dry-run: TWILIO_* env not set",
                )
                for c in targets
            ]

        # Pre-flight: twilio.rest must be importable in this process. Fail
        # fast for all contacts if the dependency is missing.
        try:
            from twilio.rest import Client  # noqa: F401
        except Exception:
            logger.warning("TwilioNotifier: twilio package not installed")
            return [
                SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False,
                    detail="twilio package not installed",
                )
                for c in targets
            ]

        twiml = self._build_twiml(payload)

        async def _call_one(c: Contact) -> SendResult:
            if not c.phone:
                return SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False, detail="contact has no phone number",
                )
            try:
                # Fresh Client per call — requests.Session inside twilio
                # is not thread-safe; constructing a Client is cheap.
                client = Client(TWILIO_SID, TWILIO_TOKEN)
                call = await asyncio.to_thread(
                    client.calls.create,
                    to=c.phone,
                    from_=TWILIO_FROM,
                    twiml=twiml,
                    timeout=20,
                )
                return SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=bool(call.sid),
                    detail=f"call_sid={call.sid}" if call.sid else "no sid returned",
                )
            except Exception as e:
                logger.warning("TwilioNotifier: call failed for %s: %s", c.id, e)
                return SendResult(
                    notifier=self.name, contact_id=c.id,
                    success=False,
                    detail=f"exception: {type(e).__name__}: {e}",
                )

        # Parallelise calls — same pattern NotifierBus uses across notifiers.
        return await asyncio.gather(*(_call_one(c) for c in targets))

    @staticmethod
    def _build_twiml(payload: AlertPayload) -> str:
        """TwiML using <Say> for the spoken message.

        No <Gather> is used because AeroGraph does not expose a Twilio
        callback URL publicly (the system runs locally during the hack).
        The call simply announces the alert and hangs up. Stops require
        the recipient to use the dashboard (not actionable from DTMF).
        """
        user = payload.user_name or "the user"
        loc = payload.location_name or "an unknown location"
        msg = (
            f"Hello. This is AeroGraph, the safety system for {user}. "
            f"We have not received a response from them in the last 30 seconds "
            f"and a possible fall was detected at {loc}. "
            f"Please try to reach them. The alert will not be repeated "
            f"automatically. Goodbye."
        )
        # Escape XML-special chars so the TwiML stays well-formed.
        msg = (msg.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
              f'<Say voice="Polly.Joanna">{msg}</Say>'
            '</Response>'
        )
