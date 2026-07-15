"""Session management endpoints for AeroGraph.

POST /session/start               — begin a new capture session
POST /session/{id}/stop           — finish a session
GET  /session/{id}/objects        — list deduplicated objects seen
GET  /session/{id}/scenes         — list raw scenes
GET  /sessions                    — list every known session
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline import registry

router = APIRouter(prefix="/v1", tags=["session"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class SessionStartRequest(BaseModel):
    location_name: str = Field(..., min_length=1, max_length=128)


class SessionStartResponse(BaseModel):
    session_id: str
    location_name: str
    started_at: float


class SessionStopResponse(BaseModel):
    session_id: str
    location_name: str
    object_count: int
    scene_count: int
    stopped_at: float


class ObjectListResponse(BaseModel):
    session_id: str
    location_name: str
    objects: list[dict]


class SceneListResponse(BaseModel):
    session_id: str
    scenes: list[dict]


class SessionListResponse(BaseModel):
    sessions: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/session/start", response_model=SessionStartResponse)
def session_start(body: SessionStartRequest) -> SessionStartResponse:
    sg = registry.get_spatial_graph()
    manifest = sg.start_session(body.location_name)
    return SessionStartResponse(
        session_id=manifest["session_id"],
        location_name=manifest["location_name"],
        started_at=manifest["started_at"],
    )


@router.post("/session/{session_id}/stop", response_model=SessionStopResponse)
def session_stop(session_id: str) -> SessionStopResponse:
    sg = registry.get_spatial_graph()
    manifest = sg.stop_session(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    summary = sg._summary(manifest)
    return SessionStopResponse(
        session_id=summary["session_id"],
        location_name=summary["location_name"],
        object_count=summary["object_count"],
        scene_count=summary["scene_count"],
        stopped_at=manifest["stopped_at"],
    )


@router.get("/session/{session_id}/objects", response_model=ObjectListResponse)
def session_objects(session_id: str) -> ObjectListResponse:
    sg = registry.get_spatial_graph()
    manifest = sg.get_manifest(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return ObjectListResponse(
        session_id=session_id,
        location_name=manifest["location_name"],
        objects=sg.get_objects(session_id),
    )


@router.get("/session/{session_id}/scenes", response_model=SceneListResponse)
def session_scenes(session_id: str) -> SceneListResponse:
    sg = registry.get_spatial_graph()
    manifest = sg.get_manifest(session_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return SceneListResponse(
        session_id=session_id,
        scenes=sg.get_scenes(session_id),
    )


@router.get("/sessions", response_model=SessionListResponse)
def sessions_list() -> SessionListResponse:
    sg = registry.get_spatial_graph()
    return SessionListResponse(sessions=sg.list_sessions())
