"""Temporal diff endpoints for AeroGraph.

POST /v1/diff/compare    — diff two explicit sessions
POST /v1/diff/location   — diff by location (auto-finds the previous session)
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


class DiffResponse(BaseModel):
    reference_session: dict
    current_session: dict
    location_name: str | None
    changes: list[dict]
    summary: dict


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
