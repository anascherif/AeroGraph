"""Stage 2 — Spatial Graph for AeroGraph.

A per-session "spatial memory" built from the live detection stream.

Design
------
Because the camera moves with the user, raw pixel coordinates are not a
stable "where".  Instead of pretending we can build a metric map, we group
detections into **scenes** (short time windows where the camera was pointing
at roughly the same area) and record, for each scene:

* which objects appeared (class + frame count + confidence)
* which other objects **co-occurred** with them (so we can later say
  "your keys were near the table")
* the last in-frame centroid / bbox of the object in that scene (so a live
  query can answer "on your left, fairly close")

Sessions are persisted as one JSON file per session under ``SESSIONS_DIR``.
ChromaDB is deliberately *not* used here — it is reserved for Stage 4 where
CLIP image embeddings genuinely need vector similarity search.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.config import (
    SESSIONS_DIR,
    SCENE_WINDOW_S,
    SIGHTING_GAP_S,
    MIN_FRAMES_FOR_STABLE,
)

logger = logging.getLogger("aerograph.spatial_graph")


# ---------------------------------------------------------------------------
# Data shapes (kept as plain dicts for JSON friendliness)
# ---------------------------------------------------------------------------
#
# A *sighting* is one observation of an object inside one scene:
#   {
#     "class": "chair",
#     "frame_count": 14,
#     "first_seen": 1723456789.12,
#     "last_seen": 1723456792.05,
#     "last_bbox": [x1, y1, x2, y2],
#     "last_centroid": [cx, cy],
#     "avg_confidence": 0.91,
#     "frame_w": 640, "frame_h": 480,
#   }
#
# A *scene* is a time window with a set of sightings keyed by class:
#   {
#     "index": 0,
#     "start": 1723456789.12,
#     "end": 1723456792.05,
#     "sightings": { "chair": {sighting}, "table": {sighting}, ... }
#   }
#
# A *session manifest* is the whole session record:
#   {
#     "session_id": "session_<uuid>",
#     "location_name": "kitchen",
#     "started_at": 1723456789.12,
#     "stopped_at": null,
#     "scenes": [ {scene}, {scene}, ... ]
#   }


class SpatialGraph:
    """Per-session spatial memory backed by JSON manifest files.

    One instance is shared across the API (see :mod:`backend.pipeline.registry`).
    All public methods are safe to call concurrently from the request thread
    *or* the WebSocket detection loop — they only touch local state + a JSON
    file write, which is atomic enough for a single-process demo server.
    """

    def __init__(self, sessions_dir: Path = SESSIONS_DIR) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # session_id -> manifest dict (in-memory cache of active sessions)
        self._active: dict[str, dict[str, Any]] = {}
        logger.info("SpatialGraph ready (sessions dir: %s)", self.sessions_dir)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def start_session(self, location_name: str) -> dict[str, Any]:
        """Create a new capture session and return its manifest header."""
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = time.time()
        manifest = {
            "session_id": session_id,
            "location_name": location_name,
            "started_at": now,
            "stopped_at": None,
            "scenes": [],
        }
        self._active[session_id] = manifest
        self._persist(manifest)
        logger.info("Session started: %s @ %s", session_id, location_name)
        return manifest

    def stop_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Mark a session as stopped and persist the final manifest."""
        manifest = self._active.pop(session_id, None)
        if manifest is None:
            # maybe it was never opened in this process — try loading from disk
            manifest = self._load(session_id)
            if manifest is None:
                return None
        manifest["stopped_at"] = time.time()
        self._persist(manifest)
        logger.info(
            "Session stopped: %s (%d scenes)",
            session_id,
            len(manifest["scenes"]),
        )
        return manifest

    def is_active(self, session_id: str) -> bool:
        return session_id in self._active

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def add_detections(
        self,
        session_id: str,
        detections: list[dict[str, Any]],
        frame_shape: tuple[int, int],  # (H, W)
        timestamp: Optional[float] = None,
    ) -> dict[str, Any]:
        """Merge a frame's detections into the session's current scene.

        Returns a small summary dict (handy for logging / WS ack).
        """
        if not detections:
            return {"added": 0, "updated": 0, "scene_index": None}

        manifest = self._active.get(session_id)
        if manifest is None:
            raise KeyError(f"Session {session_id} is not active.")

        ts = timestamp if timestamp is not None else time.time()
        frame_h, frame_w = frame_shape

        # --- 1. pick / open the current scene ---
        scene = self._current_scene(manifest, ts)
        sightings: dict[str, dict[str, Any]] = scene["sightings"]

        added = 0
        updated = 0

        # --- 2. fold each detection into the scene ---
        for det in detections:
            cls = det["class"]
            centroid = det["centroid"]
            bbox = det["bbox"]
            conf = det["confidence"]

            if cls not in sightings:
                # new object for this scene
                sightings[cls] = {
                    "class": cls,
                    "frame_count": 1,
                    "first_seen": ts,
                    "last_seen": ts,
                    "last_bbox": bbox,
                    "last_centroid": centroid,
                    "avg_confidence": conf,
                    "frame_w": frame_w,
                    "frame_h": frame_h,
                }
                added += 1
            else:
                s = sightings[cls]
                # running average confidence (cheap)
                n = s["frame_count"]
                s["avg_confidence"] = round(
                    (s["avg_confidence"] * n + conf) / (n + 1), 3
                )
                s["frame_count"] = n + 1
                s["last_seen"] = ts
                s["last_bbox"] = bbox
                s["last_centroid"] = centroid
                s["frame_w"] = frame_w
                s["frame_h"] = frame_h
                # gap too big -> this counts as a fresh sighting of the same class
                # (object left and re-entered the scene). We keep it as one entry
                # for now; Phase 3 diffing can use timestamps to distinguish.
                updated += 1

        scene["end"] = ts
        # persist roughly every few frames to avoid disk thrash
        if scene.get("persist_counter", 0) % 10 == 0:
            self._persist(manifest)
        scene["persist_counter"] = scene.get("persist_counter", 0) + 1

        return {"added": added, "updated": updated, "scene_index": scene["index"]}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_manifest(self, session_id: str) -> Optional[dict[str, Any]]:
        """Return the full manifest for a session (active or on-disk)."""
        if session_id in self._active:
            return self._active[session_id]
        return self._load(session_id)

    def get_objects(self, session_id: str) -> list[dict[str, Any]]:
        """Return the deduplicated object list across all scenes of a session."""
        manifest = self.get_manifest(session_id)
        if manifest is None:
            return []
        # Collapse sightings across scenes: keep the most-recent sighting per class
        # but annotate which scenes it appeared in (+ co-occurrence).
        by_class: dict[str, dict[str, Any]] = {}
        for scene in manifest["scenes"]:
            for cls, s in scene["sightings"].items():
                co = [
                    other
                    for other in scene["sightings"].keys()
                    if other != cls
                ]
                if cls not in by_class:
                    by_class[cls] = {
                        "class": cls,
                        "total_frames": s["frame_count"],
                        "first_seen": s["first_seen"],
                        "last_seen": s["last_seen"],
                        "last_bbox": s["last_bbox"],
                        "last_centroid": s["last_centroid"],
                        "avg_confidence": s["avg_confidence"],
                        "scenes_seen_in": [scene["index"]],
                        "co_occurred_with": set(co),
                    }
                else:
                    e = by_class[cls]
                    e["total_frames"] += s["frame_count"]
                    if s["last_seen"] > e["last_seen"]:
                        e["last_seen"] = s["last_seen"]
                        e["last_bbox"] = s["last_bbox"]
                        e["last_centroid"] = s["last_centroid"]
                    e["scenes_seen_in"].append(scene["index"])
                    e["co_occurred_with"].update(co)
        # finalise: sets -> sorted lists, apply stability filter
        out: list[dict[str, Any]] = []
        for cls, e in by_class.items():
            if e["total_frames"] < MIN_FRAMES_FOR_STABLE:
                continue
            e["co_occurred_with"] = sorted(e["co_occurred_with"])
            e.pop("scenes_seen_in")  # keep response tidy
            out.append(e)
        out.sort(key=lambda d: d["last_seen"], reverse=True)
        return out

    def get_scenes(self, session_id: str) -> list[dict[str, Any]]:
        """Return the raw scene list for a session."""
        manifest = self.get_manifest(session_id)
        if manifest is None:
            return []
        return manifest["scenes"]

    def list_sessions(self) -> list[dict[str, Any]]:
        """List every session known on disk (active + stopped)."""
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        # active first
        for sid, m in self._active.items():
            seen.add(sid)
            out.append(self._summary(m))
        # then any others on disk
        for f in sorted(self.sessions_dir.glob("session_*.json")):
            sid = f.stem
            if sid in seen:
                continue
            m = self._load(sid)
            if m is not None:
                out.append(self._summary(m))
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _current_scene(self, manifest: dict[str, Any], ts: float) -> dict[str, Any]:
        scenes = manifest["scenes"]
        if scenes:
            last = scenes[-1]
            # extend the current scene if we're still inside its window
            if ts - last["end"] <= SCENE_WINDOW_S:
                return last
            # if the same class re-appears after a long gap we still start a new
            # scene (treated as the camera pointing somewhere else and back).
        scene = {
            "index": len(scenes),
            "start": ts,
            "end": ts,
            "sightings": {},
            "persist_counter": 0,
        }
        scenes.append(scene)
        return scene

    def _summary(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": manifest["session_id"],
            "location_name": manifest["location_name"],
            "started_at": manifest["started_at"],
            "stopped_at": manifest["stopped_at"],
            "object_count": len(
                {
                    cls
                    for scene in manifest["scenes"]
                    for cls in scene["sightings"].keys()
                }
            ),
            "scene_count": len(manifest["scenes"]),
        }

    def _persist(self, manifest: dict[str, Any]) -> None:
        path = self.sessions_dir / f"{manifest['session_id']}.json"
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, default=_json_default, indent=2)
        tmp.replace(path)  # atomic on the same filesystem

    def _load(self, session_id: str) -> Optional[dict[str, Any]]:
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read session file %s", path)
            return None


def _json_default(obj: Any) -> Any:
    # sets -> sorted lists (for co_occurred_with)
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")
