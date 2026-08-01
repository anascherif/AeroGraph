"""Temporal diff endpoints for AeroGraph.

POST /v1/diff/compare    — diff two explicit sessions
POST /v1/diff/location   — diff by location (auto-finds the previous session)
POST /v1/diff/live       — diff the live camera snapshot vs the last visit
                            at the same location (or an explicit location)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline import registry
from backend.pipeline.temporal_diff import TemporalDiff

router = APIRouter(prefix="/v1", tags=["diff"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class DiffCompareRequest(BaseModel):
    reference_session_id: str = Field(..., min_length=1)
    current_session_id: str = Field(..., min_length=1)


class DiffLocationRequest(BaseModel):
    location_name: str = Field(..., min_length=1)
    current_session_id: str = Field(..., min_length=1)


class DiffLiveRequest(BaseModel):
    location_name: str = Field(..., min_length=1)
    session_id: str = Field(default="")


class DiffResponse(BaseModel):
    reference_session: dict
    current_session: dict
    location_name: str | None
    changes: list[dict]
    summary: dict
    live: bool | None = None


def _get_diff() -> TemporalDiff:
    return TemporalDiff(registry.get_spatial_graph())


@router.post("/diff/compare", response_model=DiffResponse)
def diff_compare(body: DiffCompareRequest) -> DiffResponse:
    diff = _get_diff()
    result = diff.compare(body.reference_session_id, body.current_session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find one or both sessions: "
                   f"{body.reference_session_id}, {body.current_session_id}",
        )
    return DiffResponse(**result)


@router.post("/diff/location", response_model=DiffResponse)
def diff_location(body: DiffLocationRequest) -> DiffResponse:
    diff = _get_diff()
    result = diff.compare_by_location(body.location_name, body.current_session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No previous session at '{body.location_name}' found, "
                   f"or current session '{body.current_session_id}' does not exist.",
        )
    return DiffResponse(**result)


@router.post("/diff/live", response_model=DiffResponse)
def diff_live(body: DiffLiveRequest) -> DiffResponse:
    """Compare the live camera snapshot against the last visit at
    ``location_name``.

    Requires:
      * the camera stream has produced at least one frame
      * at least one previous *stopped* session exists at ``location_name``
    """
    cam = registry.get_camera_stream()
    if cam is None:
        raise HTTPException(status_code=503, detail="Camera stream not initialised.")
    snap = cam.get_live_snapshot()
    if snap is None:
        raise HTTPException(
            status_code=503,
            detail="Live camera has not produced any frames yet. "
                   "Start a session and let the camera run for a moment.",
        )

    # If no explicit session_id provided, use the one the camera is bound to.
    live_sid = body.session_id or snap.get("session_id", "")

    diff = _get_diff()
    result = diff.compare_live_to_location(body.location_name, snap, live_sid)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No previous session at '{body.location_name}' found. "
                   f"Start a session at this location, stop it, then come back "
                   f"and try again.",
        )
    return DiffResponse(**result)
