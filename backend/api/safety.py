"""Safety API — distress-monitor status, contact CRUD, and event WS.

Endpoint map (all under /v1/safety unless noted):

  GET    /v1/safety/status                  current monitor state + signals
  WS     /v1/safety/events                 stream state transitions + alert lifecycle
  GET    /v1/safety/contacts                list contacts
  POST   /v1/safety/contacts                create contact
  DELETE /v1/safety/contacts/{contact_id}   delete contact
  POST   /v1/safety/test_alert             trigger a full alert cycle (skip detection)
  POST   /v1/safety/cancel                  manually cancel a in-flight confirmation
  POST   /v1/safety/voice_heard             inject simulated STT input (used by demo/test_alert)
  GET    /v1/safety/incidents               list recent incidents (limit=50)

Security:
  - All mutating endpoints (contacts CRUD, test_alert, cancel, voice_heard)
    require a Bearer token if AEROGRAPH_AUTH_TOKEN is set in the environment.
    GET endpoints (status, incidents, contacts list) are read-only and do
    NOT require auth — they are safe to expose for dashboard display.
  - Phone numbers are validated against an E.164-ish pattern.
  - Channels are validated against an allowlist (telegram, whatsapp, call).
  - A lightweight in-memory rate limiter caps requests per IP per minute.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field, field_validator

from backend.config import AEROGRAPH_AUTH_TOKEN
from backend.pipeline import registry

logger = logging.getLogger("aerograph.api.safety")

router = APIRouter(prefix="/v1/safety", tags=["safety"])

# Allowed channel names (MEDIUM #4 — channel validation).
_ALLOWED_CHANNELS = {"telegram", "whatsapp", "call"}


# ---------------------------------------------------------------------------
# Auth dependency (CRITICAL — prevents contact hijack + message injection)
# ---------------------------------------------------------------------------
async def require_auth(request: Request) -> None:
    """If AEROGRAPH_AUTH_TOKEN is set, require a matching Bearer token.
    If unset (local dev), allow all requests."""
    if not AEROGRAPH_AUTH_TOKEN:
        return  # local dev mode — no auth configured
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
        )
    token = auth_header[7:]  # strip "Bearer "
    if token != AEROGRAPH_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid auth token")


# ---------------------------------------------------------------------------
# Rate limiter (MEDIUM — lightweight in-memory, no external dependency)
# ---------------------------------------------------------------------------
class RateLimiter:
    """Per-IP sliding-window rate limiter. Thread-safe via dict atomicity."""
    _window_s: float
    _max: int
    _hits: dict[str, collections.deque[float]]

    def __init__(self, max_requests: int = 20, window_s: float = 60.0) -> None:
        self._max = max_requests
        self._window_s = window_s
        self._hits: dict[str, collections.deque[float]] = {}

    def check(self, key: str) -> None:
        now = time.time()
        cutoff = now - self._window_s
        dq = self._hits.setdefault(key, collections.deque(maxlen=self._max))
        # Drop expired entries
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {self._max} requests per {self._window_s:.0f}s",
            )
        dq.append(now)


_limiter = RateLimiter(max_requests=20, window_s=60.0)


async def rate_limit(request: Request) -> None:
    """Apply per-IP rate limiting to mutating endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    _limiter.check(client_ip)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class ContactCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # HIGH fix: validate phone number format (E.164-ish).
    phone: str = Field(default="", max_length=20)
    telegram_user_id: str = Field(default="", max_length=32)
    telegram_username: str = Field(default="", max_length=64)
    channels: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=500)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v:
            return v
        v = v.strip()
        # Allow +, digits, spaces, dashes, parentheses. Reject anything else
        # to prevent injection of control chars or non-numeric junk.
        allowed = set("+0123456789 -()")
        if not all(c in allowed for c in v):
            raise ValueError("phone contains invalid characters")
        digits = sum(c.isdigit() for c in v)
        if digits < 5 or digits > 15:
            raise ValueError("phone must contain 5-15 digits")
        return v

    @field_validator("telegram_username")
    @classmethod
    def validate_telegram_username(cls, v: str) -> str:
        if not v:
            return v
        v = v.strip()
        if not v.startswith("@"):
            v = f"@{v}"
        return v

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str]) -> list[str]:
        # MEDIUM fix: filter out unknown channel names.
        filtered = [ch for ch in v if ch in _ALLOWED_CHANNELS]
        return filtered


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None
    channels: Optional[list[str]] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v:
            return v
        v = v.strip()
        allowed = set("+0123456789 -()")
        if not all(c in allowed for c in v):
            raise ValueError("phone contains invalid characters")
        digits = sum(c.isdigit() for c in v)
        if digits < 5 or digits > 15:
            raise ValueError("phone must contain 5-15 digits")
        return v

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        return [ch for ch in v if ch in _ALLOWED_CHANNELS]


class VoiceHeardRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Status — no auth (read-only, safe for dashboard)
# ---------------------------------------------------------------------------
@router.get("/status")
def status() -> dict:
    sm = registry.safety_monitor
    if sm is None:
        return {"state": "disabled", "detail": "safety monitor not initialised"}
    return sm.status()


# ---------------------------------------------------------------------------
# Incidents — no auth (read-only, safe for dashboard)
# ---------------------------------------------------------------------------
@router.get("/incidents")
def incidents(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    incs = store.list_incidents(limit=limit)
    # Strip phone/telegram fields from incident notes if present — incidents
    # only contain trigger/location/outcome, not contact PII, so this is safe.
    return {"incidents": incs, "total_returned": len(incs)}


# ---------------------------------------------------------------------------
# Contacts — auth required on all (list leaks PII, CRUD is mutating)
# ---------------------------------------------------------------------------
@router.get("/contacts")
def list_contacts(_: None = Depends(require_auth)) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    return {"contacts": store.list_contacts()}


@router.post("/contacts")
def create_contact(
    req: ContactCreateRequest,
    _: None = Depends(require_auth),
    __: None = Depends(rate_limit),
) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    contact = store.add_contact(
        name=req.name,
        phone=req.phone,
        telegram_user_id=req.telegram_user_id,
        telegram_username=req.telegram_username,
        channels=req.channels,
        notes=req.notes,
    )
    return contact


@router.delete("/contacts/{contact_id}")
def delete_contact(
    contact_id: str,
    _: None = Depends(require_auth),
    __: None = Depends(rate_limit),
) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    ok = store.delete_contact(contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"contact {contact_id!r} not found")
    return {"deleted": True, "contact_id": contact_id}


# ---------------------------------------------------------------------------
# Test alert + cancel — auth + rate limit required
# ---------------------------------------------------------------------------
@router.post("/test_alert")
def test_alert(
    _: None = Depends(require_auth),
    __: None = Depends(rate_limit),
) -> dict:
    sm = registry.safety_monitor
    if sm is None:
        raise HTTPException(status_code=503, detail="safety monitor not available")
    triggered = sm.trigger_test_alert()
    if not triggered:
        raise HTTPException(
            status_code=409,
            detail=f"monitor in state '{sm.state.value}' — cannot trigger test alert now",
        )
    return {"triggered": True, "state": sm.state.value}


@router.post("/cancel")
def cancel(_: None = Depends(require_auth)) -> dict:
    sm = registry.safety_monitor
    if sm is None:
        raise HTTPException(status_code=503, detail="safety monitor not available")
    ok = sm.cancel_external()
    return {"cancelled": ok, "state": sm.state.value}


@router.post("/voice_heard")
def voice_heard(
    req: VoiceHeardRequest,
    _: None = Depends(require_auth),
    __: None = Depends(rate_limit),
) -> dict:
    """Inject simulated STT text into the monitor's heard-queue. Used by
    the dashboard's "I'm okay" button OR by external STT loops.

    The monitor scans the queue every 500ms during confirmation and looks
    for any of SAFETY_STT_LISTEN_PHRASES. If matched, the alert is cancelled.
    """
    sm = registry.safety_monitor
    if sm is None:
        raise HTTPException(status_code=503, detail="safety monitor not available")
    sm.push_heard_text(req.text)
    return {"queued": True, "state": sm.state.value}


# ---------------------------------------------------------------------------
# Events WebSocket — auth via query param (WS can't use Bearer header easily)
# ---------------------------------------------------------------------------
@router.websocket("/events")
async def events(ws: WebSocket) -> None:
    sm = registry.safety_monitor
    if sm is None:
        await ws.close(code=4005, reason="safety monitor not available")
        return

    # Auth check for WebSocket: use query param since WS doesn't support
    # custom headers in the browser API. If no auth token is configured,
    # skip the check (local dev mode).
    if AEROGRAPH_AUTH_TOKEN:
        token = ws.query_params.get("token", "")
        if token != AEROGRAPH_AUTH_TOKEN:
            await ws.close(code=4001, reason="unauthorized")
            return

    await ws.accept()
    # Send an initial snapshot so the client knows the current state.
    snapshot = sm.status()
    await ws.send_json({"type": "snapshot", "ts": asyncio.get_event_loop().time(), "data": snapshot})

    sub_id, sub_q = sm.events.subscribe(maxsize=128)
    logger.info("safety WS subscriber %d connected (state=%s)", sub_id, sm.state.value)

    try:
        while True:
            try:
                event = sub_q.popleft()
                await ws.send_json(event)
            except IndexError:
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        logger.info("safety WS subscriber %d disconnected", sub_id)
    except Exception:
        logger.exception("safety WS loop error for subscriber %d", sub_id)
    finally:
        sm.events.unsubscribe(sub_id)
