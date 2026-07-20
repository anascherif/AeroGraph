"""Multi-channel alert notifiers for the AeroGraph safety subsystem.

Notifiers are constructed once at FastAPI startup (via ``NotifierBus``) and
sent an :class:`AlertPayload` on escalation. Every notifier implements the
:class:`Notifier` Protocol defined in ``base.py``.

Channels shipped:
    - TelegramNotifier   (``telegram.py``)   — primary, free
    - WhatsAppNotifier   (``whatsapp.py``)   — via local Baileys bridge
    - TwilioNotifier     (``twilio.py``)     — env-guarded voice call
"""

from backend.notifiers.base import (
    AlertPayload,
    Contact,
    Notifier,
    SendResult,
    filter_contacts_for_channel,
)

__all__ = [
    "AlertPayload",
    "Contact",
    "Notifier",
    "SendResult",
    "filter_contacts_for_channel",
]
