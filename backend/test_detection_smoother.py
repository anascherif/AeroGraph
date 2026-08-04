"""Tests for the per-class detection smoother.

These tests verify the three properties of the smoother:

1. A class visible in >= MIN_HITS of the last WINDOW frames is emitted.
2. A class that flickers (visible 1-of-5) is suppressed.
3. A class that was emitted and disappears is held for COOLDOWN_S.
4. After COOLDOWN_S, a missing class is dropped.
5. Empty input returns empty output.
6. The most-recent sighting's bbox is the one emitted.
"""

from __future__ import annotations

import time

from backend.pipeline.detection_smoother import DetectionSmoother


def _det(cls: str, conf: float = 0.8, bbox: list[int] | None = None) -> dict:
    if bbox is None:
        bbox = [10, 10, 50, 50]
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2
    return {
        "class": cls,
        "bbox": bbox,
        "centroid": [cx, cy],
        "confidence": conf,
    }


def test_stable_class_is_emitted() -> None:
    """A class present in every frame of the window is emitted from frame 3 onward."""
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    t = 1000.0
    out_history = []
    for _ in range(5):
        out = sm.smooth([_det("bottle", 0.9)], t)
        out_history.append([d["class"] for d in out])
        t += 0.125
    # On frames 3, 4, 5 the bottle has hits 3, 4, 5 → emitted.
    assert out_history[2] == ["bottle"]
    assert out_history[3] == ["bottle"]
    assert out_history[4] == ["bottle"]


def test_single_frame_hallucination_is_suppressed() -> None:
    """A class that appears in only 1 frame out of 5 is never emitted."""
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    t = 2000.0
    # Frames 0..4: only frame 0 has the hallucinated "person".
    out0 = sm.smooth([_det("person", conf=0.80)], t)
    out1 = sm.smooth([], t + 0.125)
    out2 = sm.smooth([], t + 0.250)
    out3 = sm.smooth([], t + 0.375)
    out4 = sm.smooth([], t + 0.500)
    assert out0 == [], f"frame 0 should not emit yet, got {out0}"
    assert out1 == [], f"frame 1 should not emit yet, got {out1}"
    assert out2 == [], f"frame 2 should not emit yet, got {out2}"
    assert out3 == [], f"frame 3 should drop the class, got {out3}"
    assert out4 == [], f"frame 4 should drop the class, got {out4}"


def test_cooldown_holds_class_after_disappearance() -> None:
    """Once a class is being emitted, it stays visible for COOLDOWN_S
    even if YOLO stops detecting it."""
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    t = 3000.0
    # Prime: 5 frames seeing the bottle → emitting.
    for _ in range(5):
        sm.smooth([_det("bottle")], t)
        t += 0.125
    # Sanity: bottle is active.
    assert any(d["class"] == "bottle" for d in sm.smooth([_det("bottle")], t))

    # Now YOLO loses the bottle. We should still emit it for 1.5s.
    # 1.5s at ~125ms/frame = ~12 frames of hold.
    seen_classes = []
    for _ in range(15):
        out = sm.smooth([], t)
        seen_classes.append([d["class"] for d in out])
        t += 0.125
    # Bottle should still be present in the held frames (<= 1.5s = 12 frames).
    held_count = sum(1 for s in seen_classes if "bottle" in s)
    assert held_count >= 10, f"Expected hold for ~12 frames, only got {held_count}"

    # After cooldown elapses (say, frame 14 = 1.75s later), bottle is gone.
    out_final = sm.smooth([], t)
    assert all(d["class"] != "bottle" for d in out_final), \
        f"Bottle should be dropped after cooldown, got {out_final}"


def test_empty_input_returns_empty_output() -> None:
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    assert sm.smooth([], time.time()) == []


def test_most_recent_sighting_bbox_used() -> None:
    """When a class moves between frames, the emitted bbox is from the
    most recent *non-None* sighting."""
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    t = 4000.0
    # Prime with bbox A.
    for _ in range(3):
        sm.smooth([_det("cup", bbox=[10, 10, 20, 20])], t)
        t += 0.125
    # Now bbox shifts to B in the most recent frame.
    out = sm.smooth([_det("cup", bbox=[100, 100, 110, 110])], t)
    cup = next(d for d in out if d["class"] == "cup")
    assert cup["bbox"] == [100, 100, 110, 110]


def test_smoother_handles_interleaved_classes() -> None:
    """Two classes appearing on alternating frames each cross the 3-of-5
    threshold when their hits accumulate."""
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)
    t = 5000.0
    # 5 frames: chair in 0,2,4 ; couch in 1,3 (and 5).
    out4 = sm.smooth([_det("chair")], t); t += 0.125
    out5 = sm.smooth([_det("couch")], t); t += 0.125
    out6 = sm.smooth([_det("chair")], t); t += 0.125
    out7 = sm.smooth([_det("couch")], t); t += 0.125
    out8 = sm.smooth([_det("chair")], t); t += 0.125
    out9 = sm.smooth([_det("couch")], t)

    # chair seen on frames 0,2,4,6,8 — 5 hits so should be emitting by frame 8.
    assert any(d["class"] == "chair" for d in out8)
    # couch seen on frames 1,3,5,7,9 — 4 hits by frame 9, should emit at frame 9.
    assert any(d["class"] == "couch" for d in out9)
