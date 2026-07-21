"""NotifierBus — routes an AlertPayload to all enabled notifiers in parallel.

On escalate():
  bus.send_all(contacts, payload) → dict[str, list[SendResult]]

Each notifier runs concurrently. A failure in one NEVER aborts another.
The result dict is keyed by notifier name ("telegram", "whatsapp", "twilio")
so the dashboard can render a per-channel status badge.

The bus is constructed at app startup with all three notifiers. Notifiers
self-disable gracefully (return success=False with a "dry-run" or
"unconfigured" detail) when env vars are missing — so we just always send
to all three and let them decide individually per contact.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from backend.notifiers.base import (
    AlertPayload, Contact, Notifier, SendResult,
)
from backend.notifiers.telegram import TelegramNotifier
from backend.notifiers.whatsapp import WhatsAppNotifier
from backend.notifiers.twilio import TwilioNotifier

logger = logging.getLogger("aerograph.notifier_bus")


class NotifierBus:
    def __init__(self, notifiers: Iterable[Notifier] | None = None) -> None:
        if notifiers is None:
            notifiers = [
                TelegramNotifier(),
                WhatsAppNotifier(),
                TwilioNotifier(),
            ]
        # notifiers is iterable; keep ordering deterministic.
        self._notifiers: list[Notifier] = list(notifiers)
        names = ", ".join(n.name for n in self._notifiers)
        logger.info("NotifierBus ready: %s", names)

    async def send_all(
        self,
        contacts: list[Contact],
        payload: AlertPayload,
    ) -> dict[str, list[SendResult]]:
        """Run all notifiers in parallel. Returns per-notifier results.

        Uses asyncio.gather(return_exceptions=True) so a buggy notifier
        raising an exception becomes a failed SendResult rather than
        aborting the others.
        """
        if not contacts:
            logger.warning("NotifierBus.send_all called with no contacts — skipping")
            return {n.name: [] for n in self._notifiers}

        async def _safe_call(notifier: Notifier) -> list[SendResult]:
            try:
                res = await notifier.send(contacts, payload)
                if not isinstance(res, list):
                    return [SendResult(
                        notifier=notifier.name, contact_id="",
                        success=False, detail=f"notifier returned {type(res).__name__}",
                    )]
                return res
            except asyncio.CancelledError:
                # Never swallow cancellation: propagate so the caller can shut
                # down cleanly. This branch fires only if our task itself was
                # cancelled (e.g. on shutdown) — NOT if a downstream notifier
                # cancelled internally (that becomes an Exception below).
                raise
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:
                # Catches Exception + any non-Exception BaseException
                # subclasses that aren't cancellation/exit signals
                # (e.g. greenlet errors from nested libraries). The hard
                # contract is: a notifier crash never aborts the others.
                logger.exception("NotifierBus: %s crashed", notifier.name)
                return [
                    SendResult(
                        notifier=notifier.name, contact_id=c.id,
                        success=False,
                        detail=f"notifier crashed: {type(e).__name__}: {e}",
                    )
                    for c in contacts
                ]

        # return_exceptions=True is defence-in-depth: even though _safe_call
        # catches BaseException, a future refactor could regress that catch,
        # and the documented contract is "a failure never aborts the others".
        # An Exception escaping _safe_call will then be returned to us in
        # results_lists rather than causing asyncio.gather to cancel sibling
        # tasks (which would directly break the contract on Py3.8+ where
        # gather(return_exceptions=False) cancels the rest on first raise).
        tasks = [_safe_call(n) for n in self._notifiers]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        out: dict[str, list[SendResult]] = {}
        for notifier, results in zip(self._notifiers, results_lists):
            if isinstance(results, BaseException) and not isinstance(results, list):
                # _safe_call's catch was bypassed — synthesise a per-contact
                # failure list so the dashboard still gets a result shape.
                logger.error(
                    "NotifierBus: %s produced an uncaught %s: %s",
                    notifier.name, type(results).__name__, results,
                )
                out[notifier.name] = [
                    SendResult(
                        notifier=notifier.name, contact_id=c.id,
                        success=False,
                        detail=f"uncaught {type(results).__name__}: {results}",
                    )
                    for c in contacts
                ]
            else:
                out[notifier.name] = results
        # Log summary
        succeeded = sum(
            1 for results in out.values()
            for r in results if r.success
        )
        attempted = sum(len(results) for results in out.values())
        logger.info(
            "NotifierBus: %d/%d sends succeeded across %d notifiers",
            succeeded, attempted, len(self._notifiers),
        )
        return out
