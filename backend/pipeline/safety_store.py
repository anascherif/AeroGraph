"""SafetyStore — JSON-backed persistence for the safety subsystem.

Two files under ``data/safety/``:

  contacts.json   — list of family/emergency contacts.
                    [{
                       "id": "c_xxx",
                       "name": "Mom",
                       "phone": "+216...",
                       "telegram_user_id": "123456",
                       "telegram_username": "@mom",
                       "channels": ["telegram", "whatsapp", "call"],
                       "notes": "",
                       "created_at": 1721...
                    }, ...]

  incidents.json  — append-mostly incident log.
                    [{
                       "incident_id": "inc_xxx",
                       "started_at": float,
                       "resolved_at": float | None,
                       "trigger": "manual test_alert",
                       "location_name": "kitchen",
                       "session_id": "session_xxx",
                       "outcome": "cancelled_by_voice" | "cancelled_by_ui"
                                   | "escalated_and_sent" | "false_alarm",
                       "note": "...",
                    }, ...]

Thread-safe (a single lock guards all writes). Cheap — we hold the lock only
for the brief read-modify-write; not appropriate for hot loops but fine here.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("aerograph.safety_store")


class SafetyStore:
    def __init__(self, safety_dir: Path) -> None:
        self._dir = Path(safety_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._contacts_path = self._dir / "contacts.json"
        self._incidents_path = self._dir / "incidents.json"
        self._lock = threading.Lock()
        self._contacts: list[dict[str, Any]] = self._load(self._contacts_path, default=[])
        self._incidents: list[dict[str, Any]] = self._load(self._incidents_path, default=[])
        logger.info(
            "SafetyStore ready (%d contacts, %d past incidents)",
            len(self._contacts), len(self._incidents),
        )

    @staticmethod
    def _load(path: Path, *, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("SafetyStore: failed to load %s — using default", path)
            return default

    def _flush(self) -> None:
        """Persist both files. Caller must hold the lock."""
        try:
            tmp = self._contacts_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._contacts, indent=2), encoding="utf-8")
            tmp.replace(self._contacts_path)
        except Exception:
            logger.exception("SafetyStore: contacts flush failed")
        try:
            tmp = self._incidents_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._incidents, indent=2), encoding="utf-8")
            tmp.replace(self._incidents_path)
        except Exception:
            logger.exception("SafetyStore: incidents flush failed")

    # ------------------------------------------------------------------
    # Contacts CRUD
    # ------------------------------------------------------------------
    def list_contacts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(c) for c in self._contacts]

    def get_contact(self, contact_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            for c in self._contacts:
                if c.get("id") == contact_id:
                    return dict(c)
        return None

    def add_contact(
        self,
        *,
        name: str,
        phone: str = "",
        telegram_user_id: str = "",
        telegram_username: str = "",
        channels: Optional[list[str]] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        contact = {
            "id": f"c_{uuid.uuid4().hex[:12]}",
            "name": name,
            "phone": phone,
            "telegram_user_id": telegram_user_id,
            "telegram_username": telegram_username,
            "channels": channels if channels is not None else [],
            "notes": notes,
            "created_at": time.time(),
        }
        with self._lock:
            self._contacts.append(contact)
            self._flush()
        logger.info("SafetyStore: added contact %s (%s)", contact["id"], name)
        return contact

    def update_contact(self, contact_id: str, **fields) -> Optional[dict[str, Any]]:
        with self._lock:
            for c in self._contacts:
                if c.get("id") == contact_id:
                    for k, v in fields.items():
                        if k in ("name", "phone", "telegram_user_id",
                                 "telegram_username", "channels", "notes"):
                            c[k] = v
                    self._flush()
                    return dict(c)
            return None

    def delete_contact(self, contact_id: str) -> bool:
        with self._lock:
            before = len(self._contacts)
            self._contacts = [c for c in self._contacts if c.get("id") != contact_id]
            after = len(self._contacts)
            if before != after:
                self._flush()
                return True
            return False

    # ------------------------------------------------------------------
    # Incident log (append-mostly)
    # ------------------------------------------------------------------
    def append_incident(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._incidents.append(record)
            self._flush()

    def resolve_incident(
        self,
        incident_id: str,
        *,
        outcome: str,
        ts: float,
        note: str = "",
    ) -> None:
        with self._lock:
            for inc in self._incidents:
                if inc.get("incident_id") == incident_id:
                    inc["outcome"] = outcome
                    inc["resolved_at"] = ts
                    if note:
                        inc["note"] = note
                    self._flush()
                    return
            logger.warning("SafetyStore: incident %s not found for resolve", incident_id)

    def list_incidents(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(i) for i in self._incidents[-limit:]]
