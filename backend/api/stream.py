"""Live stream WebSocket endpoint for AeroGraph.

WS /v1/session/{session_id}/stream
    Subscribes to the live camera + detection loop for the given session.
    Broadcasts JSON payloads as frames are processed.

Query params:
    include_frame=true   — also send a base64-encoded JPEG preview per frame
"""

from __future__ import annotations

import base64
import logging
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from backend.pipeline import registry
from backend.pipeline.camera_stream import CameraStream
from backend.config import STREAM_JPEG_QUALITY, runtime

logger = logging.getLogger("aerograph.api.stream")

router = APIRouter(prefix="/v1", tags=["stream"])


@router.websocket("/session/{session_id}/stream")
async def session_stream(
    ws: WebSocket,
    session_id: str,
    include_frame: bool = Query(default=False),
) -> None:
    """Live detection stream for a capture session.

    On connect: validates the session exists, gets/creates the shared
    ``CameraStream``, and binds it to the session. Each new detection pass
    is pushed to the client as a JSON message.
    """
    sg = registry.get_spatial_graph()

    # validate session
    manifest = sg.get_manifest(session_id)
    if manifest is None:
        await ws.close(code=4004, reason=f"Session '{session_id}' not found")
        return

    cam = registry.get_camera_stream()
    cam.set_session(session_id)

    sub_id, sub_queue = cam.subscribe()
    runtime.camera_streaming = True

    await ws.accept()
    logger.info(
        "WS subscriber %d connected for session %s (include_frame=%s)",
        sub_id, session_id, include_frame,
    )

    # Send an initial ack so the client knows the stream is alive
    await ws.send_json({
        "type": "status",
        "session_id": session_id,
        "streaming": True,
        "include_frame": include_frame,
    })

    try:
        while True:
            payload = await _async_get(sub_queue)
            if payload is None:
                break  # stream closed

            msg = {
                "type": "frame",
                "timestamp": payload["timestamp"],
                "frame_shape": payload["frame_shape"],
                "detections": payload["detections"],
                "roll": payload["roll"],
            }

            if include_frame:
                # Encode JPEG from the latest stored frame (detections overlaid)
                snapshot = cam.get_snapshot(include_frame=True)
                if snapshot.get("available"):
                    msg["frame_b64"] = snapshot["frame_b64"]

            await ws.send_json(msg)

    except WebSocketDisconnect:
        logger.info("WS subscriber %d disconnected", sub_id)
    except Exception:
        logger.exception("WS loop error for subscriber %d", sub_id)
    finally:
        cam.unsubscribe(sub_id)
        runtime.camera_streaming = cam.subscriber_count > 0
        logger.info(
            "WS subscriber %d cleaned up (remaining: %d)",
            sub_id, cam.subscriber_count,
        )


# --- Helper ---------------------------------------------------------------
async def _async_get(q):
    """Poll a sync queue from async context, yielding to the event loop.

    Uses a short poll interval so the async WebSocket loop stays responsive
    to disconnects without blocking on the sync queue for too long.
    """
    import asyncio
    import queue as _q

    while True:
        try:
            return q.get_nowait()
        except _q.Empty:
            await asyncio.sleep(0.02)


# --- REST snapshot endpoint ----------------------------------------------
@router.get("/session/{session_id}/snapshot")
async def session_snapshot(
    session_id: str,
    include_frame: bool = Query(default=True),
) -> dict:
    """One-shot REST snapshot of the latest frame + detections."""
    if registry.camera_stream is None:
        return {"available": False, "detail": "Camera stream not active."}

    cam = registry.camera_stream
    if not cam.is_running:
        return {"available": False, "detail": "Detection loop not running."}

    return cam.get_snapshot(include_frame=include_frame)
