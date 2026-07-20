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
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field

from backend.pipeline import registry

logger = logging.getLogger("aerograph.api.safety")

router = APIRouter(prefix="/v1/safety", tags=["safety"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class ContactCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    phone: str = Field(default="")
    telegram_user_id: str = Field(default="")
    telegram_username: str = Field(default="")
    channels: list[str] = Field(default_factory=list)
    notes: str = Field(default="")


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None
    channels: Optional[list[str]] = None
    notes: Optional[str] = None


class VoiceHeardRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@router.get("/status")
def status() -> dict:
    sm = registry.safety_monitor
    if sm is None:
        return {"state": "disabled", "detail": "safety monitor not initialised"}
    return sm.status()


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------
@router.get("/incidents")
def incidents(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    incs = store.list_incidents(limit=limit)
    return {"incidents": incs, "total_returned": len(incs)}


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
@router.get("/contacts")
def list_contacts() -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    return {"contacts": store.list_contacts()}


@router.post("/contacts")
def create_contact(req: ContactCreateRequest) -> dict:
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
def delete_contact(contact_id: str) -> dict:
    store = registry.safety_store
    if store is None:
        raise HTTPException(status_code=503, detail="safety store not available")
    ok = store.delete_contact(contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"contact {contact_id!r} not found")
    return {"deleted": True, "contact_id": contact_id}


# ---------------------------------------------------------------------------
# Test alert + cancel
# ---------------------------------------------------------------------------
@router.post("/test_alert")
def test_alert() -> dict:
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
def cancel() -> dict:
    sm = registry.safety_monitor
    if sm is None:
        raise HTTPException(status_code=503, detail="safety monitor not available")
    ok = sm.cancel_external()
    return {"cancelled": ok, "state": sm.state.value}


@router.post("/voice_heard")
def voice_heard(req: VoiceHeardRequest) -> dict:
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
# Events WebSocket
# ---------------------------------------------------------------------------
@router.websocket("/events")
async def events(ws: WebSocket) -> None:
    sm = registry.safety_monitor
    if sm is None:
        await ws.close(code=4005, reason="safety monitor not available")
        return

    await ws.accept()
    # Send an initial snapshot so the client knows the current state.
    snapshot = sm.status()
    await ws.send_json({"type": "snapshot", "ts": asyncio.get_event_loop().time(), "data": snapshot})

    sub_id, sub_q = sm.events.subscribe(maxsize=128)
    logger.info("safety WS subscriber %d connected (state=%s)", sub_id, sm.state.value)

    try:
        # Poll the deque from async context — it's a collections.deque
        # (thread-safe appends from monitor), so we read in a tight loop
        # with brief async sleeps.
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
