"""Live camera stream + detection loop for AeroGraph.

Runs an OpenCV VideoCapture in a background thread, feeds frames through
the YOLO detector, pushes detections into the SpatialGraph for the active
session, and captures keyframes for the CLIP index at a throttled rate.

A single instance of this class is shared across all WebSocket subscribers
(see ``registry.camera_stream``), because there is only one physical camera.
"""

from __future__ import annotations

import base64
import logging
import queue
import threading
import time
from typing import Any

import cv2
import numpy as np

from backend.config import (
    CAMERA_SOURCE_PARSED,
    DETECTION_CLASSES,
    DETECTION_CONFIDENCE,
    KEYFRAME_INTERVAL_S,
    STREAM_FPS,
    STREAM_JPEG_QUALITY,
)

logger = logging.getLogger("aerograph.camera_stream")


class CameraStream:
    """Singleton: open camera, run detection loop, broadcast results.

    Subscribers call ``subscribe()`` to get a thread-safe queue of result
    dicts (one per processed frame). When a subscriber is done it calls
    ``unsubscribe()`` to release the queue. The detection loop keeps running
    as long as there is at least one subscriber — it shuts down automatically
    when the last subscriber leaves.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[int, queue.Queue[dict]] = {}
        self._sub_counter = 0
        self._roll_counter = 0  # prevents duplicate detection IDs

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session_id: str = ""

        # latest frame + detections (for the keyframe index / screenshots)
        self._latest_frame: np.ndarray | None = None
        self._latest_detections: list[dict] = []
        self._frame_lock = threading.Lock()

        self._last_keyframe_ts = 0.0
        self._fps_interval = 1.0 / STREAM_FPS if STREAM_FPS > 0 else 0.0

    # ------------------------------------------------------------------
    # Subscriber lifecycle
    # ------------------------------------------------------------------
    def subscribe(self) -> tuple[int, queue.Queue[dict]]:
        """Register a new subscriber. Returns ``(subscriber_id, queue)``.

        Starts the camera + detection loop on the first subscriber.
        """
        with self._lock:
            sid = self._sub_counter
            self._sub_counter += 1
            q: queue.Queue[dict] = queue.Queue(maxsize=8)
            self._subscribers[sid] = q
            n = len(self._subscribers)

        logger.info("Subscriber %d added (total: %d)", sid, n)

        if n == 1:
            self._start()
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        """Remove a subscriber. Stops the loop if no subscribers remain."""
        with self._lock:
            self._subscribers.pop(sid, None)
            n = len(self._subscribers)

        logger.info("Subscriber %d removed (remaining: %d)", sid, n)

        if n == 0:
            self._stop()

    def set_session(self, session_id: str) -> None:
        """Bind (or rebind) the stream to a capture session.

        Only one session is active at a time — detections are folded into
        this session's spatial graph.
        """
        self._session_id = session_id
        logger.info("Stream bound to session %s", session_id)

    # ------------------------------------------------------------------
    # Loop control
    # ------------------------------------------------------------------
    def _start(self) -> None:
        """Open the camera and launch the detection thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="camera-detection", daemon=True
        )
        self._thread.start()

    def _stop(self) -> None:
        """Signal the loop to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    # ------------------------------------------------------------------
    # Detection loop
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        """Main capture+detect loop. Runs until ``_stop_event`` is set."""
        from backend.pipeline import registry

        cap = cv2.VideoCapture(CAMERA_SOURCE_PARSED)
        if not cap.isOpened():
            logger.error(
                "Could not open camera source %r. Stream shutting down.",
                CAMERA_SOURCE_PARSED,
            )
            return

        logger.info("Camera opened (%r)", CAMERA_SOURCE_PARSED)

        try:
            while not self._stop_event.is_set():
                t_frame_start = time.perf_counter()

                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.warning("Empty frame from camera, retrying…")
                    time.sleep(0.1)
                    continue

                frame_h, frame_w = frame.shape[:2]

                # --- Run detection ---
                detections: list[dict] = []
                detector = registry.detector
                if detector is not None:
                    try:
                        detections = detector.detect(frame)
                    except Exception:
                        logger.exception("Detection error on current frame")

                ts = time.time()

                # --- Feed spatial graph ---
                sid = self._session_id
                sg = registry.spatial_graph
                if sid and sg is not None and sg.is_active(sid):
                    try:
                        sg.add_detections(
                            sid, detections, (frame_h, frame_w), timestamp=ts
                        )
                    except Exception:
                        logger.exception("Spatial graph ingestion error")

                # --- Capture keyframe (throttled) ---
                self._maybe_capture_keyframe(frame, sid, detections, ts)

                # --- Feed the safety monitor (cheap; inline) ---
                sm = registry.safety_monitor
                if sm is not None:
                    try:
                        sm.observe(frame, detections, ts)
                    except Exception:
                        logger.exception("Safety monitor observe() error")

                # --- Store latest for screenshots / snapshot endpoint ---
                self._roll_counter += 1
                roll = self._roll_counter
                with self._frame_lock:
                    self._latest_frame = frame.copy()
                    self._latest_detections = detections

                # --- Broadcast to subscribers ---
                payload = {
                    "timestamp": ts,
                    "frame_shape": [frame_h, frame_w],
                    "detections": detections,
                    "roll": roll,
                }
                self._broadcast(payload)

                # --- FPS throttle ---
                elapsed = time.perf_counter() - t_frame_start
                if self._fps_interval > elapsed:
                    time.sleep(self._fps_interval - elapsed)
        finally:
            cap.release()
            logger.info("Camera released")

    def _maybe_capture_keyframe(
        self,
        frame: np.ndarray,
        sid: str,
        detections: list[dict],
        ts: float,
    ) -> None:
        """Encode + store a keyframe every KEYFRAME_INTERVAL_S seconds."""
        from backend.pipeline import registry

        kfi = registry.keyframe_index
        if kfi is None:
            return
        if ts - self._last_keyframe_ts < KEYFRAME_INTERVAL_S:
            return
        self._last_keyframe_ts = ts

        # spatial graph manifest lookup for the location name
        sg = registry.spatial_graph
        loc = ""
        if sg is not None and sid:
            manifest = sg.get_manifest(sid)
            if manifest:
                loc = manifest.get("location_name", "")

        obj_classes = [d["class"] for d in detections]
        try:
            kfi.add_keyframe(
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                session_id=sid,
                location_name=loc,
                objects=obj_classes,
                timestamp=ts,
            )
        except Exception:
            logger.debug("Keyframe capture failed", exc_info=True)

    def _broadcast(self, payload: dict) -> None:
        """Push payload to every subscriber's queue (drop if full)."""
        with self._lock:
            subs = list(self._subscribers.values())
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass  # drop slow subscribers

    # ------------------------------------------------------------------
    # Utilities for the WebSocket layer
    # ------------------------------------------------------------------
    @staticmethod
    def encode_jpeg(
        frame: np.ndarray,
        detections: list[dict] | None = None,
        quality: int = STREAM_JPEG_QUALITY,
    ) -> bytes:
        """JPEG-encode a frame, optionally drawing bboxes on it.

        Returns raw JPEG bytes. The WebSocket layer can base64-encode them.
        """
        out = frame.copy()
        if detections:
            for d in detections:
                x1, y1, x2, y2 = d["bbox"]
                label = d["class"]
                conf = d["confidence"]
                # bounding box
                cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # label background
                text = f"{label} {conf:.2f}"
                (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(out, (x1, y1 - th - bl), (x1 + tw, y1), (0, 255, 0), -1)
                cv2.putText(
                    out, text, (x1, y1 - bl),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
                )
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return b""
        return buf.tobytes()

    def get_snapshot(self, include_frame: bool = False) -> dict:
        """Return the latest frame + detections as a dict.

        If ``include_frame`` is True, also returns a base64-encoded JPEG.
        """
        with self._frame_lock:
            frame = self._latest_frame
            detections = list(self._latest_detections)

        if frame is None:
            return {"available": False}

        out: dict[str, Any] = {
            "available": True,
            "frame_shape": [frame.shape[0], frame.shape[1]],
            "detections": detections,
        }
        if include_frame:
            jpeg = self.encode_jpeg(frame, detections)
            out["frame_b64"] = base64.b64encode(jpeg).decode("ascii")
        return out

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def get_live_snapshot(self) -> dict | None:
        """Return the latest detection snapshot for diff comparisons.

        Returns ``None`` if the camera has not yet produced a frame.
        Shape:
            {
              "frame_shape": [h, w],
              "detections": [{"class": str, "confidence": float,
                              "bbox": [x1, y1, x2, y2],
                              "centroid": [cx, cy]}, ...],
              "timestamp": float,
              "session_id": str,
            }
        """
        with self._frame_lock:
            frame = self._latest_frame
            detections = list(self._latest_detections)
        if frame is None:
            return None
        # Re-shape detections: include centroid for the diff engine.
        shaped: list[dict] = []
        h, w = frame.shape[:2]
        for d in detections:
            x1, y1, x2, y2 = d["bbox"]
            shaped.append({
                "class": d["class"],
                "confidence": d.get("confidence", 0.0),
                "bbox": [x1, y1, x2, y2],
                "centroid": [(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                "frame_w": w,
                "frame_h": h,
            })
        return {
            "frame_shape": [h, w],
            "detections": shaped,
            "timestamp": time.time(),
            "session_id": self._session_id,
        }
