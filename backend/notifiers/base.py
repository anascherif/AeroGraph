"""Notifier contracts — the protocol every notifier implements.

Three notifiers ship in this release:
  - TelegramNotifier  (primary)
  - WhatsAppNotifier  (via local Baileys bridge)
  - TwilioNotifier    (env-guarded, dry-run by default)

The NotifierBus (notifier_bus.py) fans out to all enabled notifiers in
parallel via asyncio.gather(..., return_exceptions=True). The failure of
any single notifier does NOT abort the others — that's a hard contract here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class AlertPayload:
    """Bundled context for a single alert fan-out."""
    incident_id: str
    user_name: str
    location_name: str
    session_id: str
    started_at: float
    trigger: str
    keyframes_jpeg: list[bytes] = field(default_factory=list)

    def summary_text(self) -> str:
        """One short human-readable line the notifiers can use verbatim."""
        import time as _t
        ts = _t.strftime("%H:%M", _t.localtime(self.started_at))
        loc = self.location_name or "unknown location"
        user = self.user_name or "the user"
        return (
            f"AeroGraph alert: {user} may need help. "
            f"Last seen at {loc} around {ts}. "
            f"No response to voice confirmation. Please check on them. "
            f"(incident {self.incident_id})"
        )


@dataclass
class Contact:
    id: str
    name: str
    phone: str = ""
    telegram_user_id: str = ""
    telegram_username: str = ""
    channels: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class SendResult:
    notifier: str          # "telegram" | "whatsapp" | "twilio"
    contact_id: str
    success: bool
    detail: str = ""       # human-readable: reason for failure or "ok"


@runtime_checkable
class Notifier(Protocol):
    """A notifier sends one payload to one or more contacts over one channel.

    All implementations MUST be safe to call concurrently. Exceptions should
    be caught internally and surfaced as SendResult(success=False, detail=...).
    Returning a non-success result never aborts the bus.
    """

    name: str  # "telegram" | "whatsapp" | "twilio"

    async def send(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> list[SendResult]:
        """Fan out within this notifier's own channel."""
        ...


def filter_contacts_for_channel(
    contacts: list[Contact], channel: str
) -> list[Contact]:
    """Return contacts whose `channels` list explicitly opts into `channel`,
    OR (when no channels selected for a contact) include them — we treat
    opt-in as the safe default to ensure contacts don't miss alerts by
    forgetting to configure channels.

    EXCEPTION: the ``"call"`` channel (Twilio outbound voice) does NOT
    participate in the empty-channels shorthand. A paid phone call to a
    landline or non-consenting number is a real-world consent violation
    (TCPA in the US, similar rules elsewhere), so a contact must explicitly
    list ``"call"`` in their channels to receive a phone call. This makes
    the safe-by-default behaviour narrower but more correct.
    """
    out = []
    for c in contacts:
        if not c.channels:
            # Empty channels = safe low-friction default. Telegram and
            # WhatsApp are reversible / no-cost. Twilio outbound calls are
            # excluded by this default — see the docstring above.
            if channel == "call":
                continue
            out.append(c)
            continue
        if channel in c.channels:
            out.append(c)
    return out
