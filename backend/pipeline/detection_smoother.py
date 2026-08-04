"""Temporal smoothing for YOLO detections.

Sits between :class:`Detector` and the spatial graph / WebSocket broadcast
to suppress single-frame hallucinations and flicker.

Design
------
For each class observed in the live stream, we keep a small rolling window
of recent sightings (the last ``WINDOW`` frames). A class is emitted as
"currently detected" only if it has been seen in at least ``MIN_HITS`` of
the last ``WINDOW`` frames.

After a class stops being detected by YOLO, we keep it visible for
``COOLDOWN_S`` seconds (hysteresis) so a 1-2 frame occlusion or motion blur
does not make it vanish and reappear on the dashboard.

The smoother keeps the *most recent* sighting dict per class (cached
separately so it survives even after the rolling window drains). The
emitted dict has the same shape as :meth:`Detector.detect` output.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Optional

from backend.config import (
    DETECTION_SMOOTHER_COOLDOWN_S,
    DETECTION_SMOOTHER_MIN_HITS,
    DETECTION_SMOOTHER_WINDOW,
)

logger = logging.getLogger("aerograph.smoother")


class DetectionSmoother:
    """Per-class rolling-window smoother for live YOLO detections.

    Thread-safety: the smoother is called from the single camera-detection
    thread, so no internal locking is required.
    """

    def __init__(
        self,
        window: int = DETECTION_SMOOTHER_WINDOW,
        min_hits: int = DETECTION_SMOOTHER_MIN_HITS,
        cooldown_s: float = DETECTION_SMOOTHER_COOLDOWN_S,
    ) -> None:
        self.window = max(1, int(window))
        self.min_hits = max(1, int(min_hits))
        self.cooldown_s = float(cooldown_s)
        if self.min_hits > self.window:
            # min_hits > window would make nothing ever qualify; clamp.
            self.min_hits = self.window

        # per-class rolling window of recent sighting dicts (or None if not
        # seen that frame). Length is bounded by `window`.
        self._history: dict[str, deque[Optional[dict]]] = {}
        # cls -> most recent non-None sighting (cached so we can still emit
        # during cooldown after the window has drained).
        self._last_sighting: dict[str, dict[str, Any]] = {}
        # cls -> timestamp of last genuine sighting (epoch seconds).
        self._last_seen: dict[str, float] = {}
        # cls -> currently emitted? (so we know when to apply the cooldown
        # hold instead of the hits-based emission).
        self._emitted: set[str] = set()

    def smooth(
        self,
        detections: list[dict[str, Any]],
        ts: float,
    ) -> list[dict[str, Any]]:
        """Smooth a single frame's detections.

        Parameters
        ----------
        detections:
            The raw output from :meth:`Detector.detect` for this frame.
        ts:
            Monotonic timestamp (epoch seconds) for the current frame.

        Returns
        -------
        list of dict
            The smoothed list of detections. Each dict has the same shape as
            the input detections: ``class``, ``bbox``, ``centroid``,
            ``confidence``. If a class is dropped due to cooldown expiry,
            it is simply not present in the output list.
        """
        # Group detections by class. If a class appears multiple times in
        # one frame (rare, but YOLO sometimes returns two overlapping
        # boxes), keep the highest-confidence sighting.
        by_class: dict[str, dict[str, Any]] = {}
        for d in detections:
            cls = d["class"]
            existing = by_class.get(cls)
            if existing is None or d.get("confidence", 0.0) > existing.get("confidence", 0.0):
                by_class[cls] = d

        # All known classes (history + new) so we can age unseen ones too.
        all_classes = set(self._history.keys()) | set(by_class.keys())

        out: list[dict[str, Any]] = []

        for cls in all_classes:
            current = by_class.get(cls)

            # Maintain the rolling window for this class.
            hist = self._history.get(cls)
            if hist is None:
                hist = deque(maxlen=self.window)
                self._history[cls] = hist
            hist.append(current)  # None if not seen this frame

            if current is not None:
                self._last_seen[cls] = ts
                self._last_sighting[cls] = current

            # Count real sightings in the window (non-None entries).
            hits = sum(1 for h in hist if h is not None)
            last_seen = self._last_seen.get(cls, 0.0)
            age = ts - last_seen

            # Decide whether to emit this class.
            should_emit = False
            if hits >= self.min_hits:
                # Active and stable: emit.
                should_emit = True
            elif cls in self._emitted and age <= self.cooldown_s:
                # Was emitted, YOLO lost it, but we're still inside the
                # cooldown hold — keep emitting the last known sighting.
                should_emit = True
            elif cls in self._emitted and age > self.cooldown_s:
                # Previously emitted, cooldown expired: drop and forget.
                self._emitted.discard(cls)
                self._history.pop(cls, None)
                self._last_seen.pop(cls, None)
                self._last_sighting.pop(cls, None)
                continue
            # else: hits < min_hits and not previously emitted — keep in
            # history so the class can accumulate hits over upcoming frames.
            # We just don't emit it yet.

            if should_emit:
                self._emitted.add(cls)
                # Use cached last sighting — always non-None here because:
                #   * if hits >= min_hits, we saw the class recently, so
                #     _last_sighting[cls] was set.
                #   * if in cooldown, we only entered that branch if
                #     `cls in self._emitted`, which means we previously had
                #     hits >= min_hits, which means _last_sighting was set.
                sighting = self._last_sighting.get(cls)
                if sighting is not None:
                    out.append(sighting)

        # Prune any stale class that's no longer in the window and not
        # currently emitted (defensive cleanup — should rarely trigger).
        for cls in list(self._history.keys()):
            if cls not in self._emitted:
                # Not emitted: if the class has not been seen recently and
                # the window is all-None, drop it to avoid unbounded growth.
                hist = self._history.get(cls)
                if hist is not None and all(h is None for h in hist):
                    last_seen = self._last_seen.get(cls, 0.0)
                    if ts - last_seen > self.cooldown_s:
                        self._history.pop(cls, None)
                        self._last_seen.pop(cls, None)
                        self._last_sighting.pop(cls, None)

        return out

    def reset(self) -> None:
        """Clear all state (e.g. when the camera stream is rebound)."""
        self._history.clear()
        self._last_sighting.clear()
        self._last_seen.clear()
        self._emitted.clear()
