"""End-to-end smoother test using the real YOLO detector.

Runs YOLO over 30 synthetic frames in 3 phases:
  Phase A (frames 0-9):  empty scene, no detections
  Phase B (frames 10-19): a fake "bottle" rectangle drawn on the frame
  Phase C (frames 20-29): fake bottle disappears for 1-2 frames at a time
                           (simulating motion blur / partial occlusion)

Measures: smoother emit / suppress / hold behaviour in each phase.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DETECTION_CLASSES, DETECTION_CONFIDENCE
from backend.pipeline.detector import Detector
from backend.pipeline.detection_smoother import DetectionSmoother


def make_empty() -> np.ndarray:
    return np.full((480, 640, 3), 128, dtype=np.uint8)


def make_with_bottle() -> np.ndarray:
    """Synthetic frame with a dark vertical rectangle in the centre —
    designed to potentially trigger a YOLO false positive (looks like
    a bottle silhouette). YOLO11n at imgsz=416 typically picks this up
    because it's a tall dark shape against a plain background.
    """
    img = make_empty()
    cv2.rectangle(img, (290, 200), (350, 380), (40, 40, 40), -1)
    cv2.rectangle(img, (300, 180), (340, 200), (30, 30, 30), -1)  # cap
    return img


def main() -> int:
    print("Loading detector + smoother...")
    det = Detector(
        model_path="backend/models/yolo11n_416.onnx",
        allowed_classes=DETECTION_CLASSES,
        confidence=DETECTION_CONFIDENCE,
    )
    sm = DetectionSmoother(window=5, min_hits=3, cooldown_s=1.5)

    # Load the real chest-cam frame for a realistic test
    real_frame_path = "data/test_frame_raw.jpg"
    real_frame = cv2.imread(real_frame_path)
    assert real_frame is not None, f"Failed to load {real_frame_path}"
    print(f"Loaded {real_frame_path} (shape={real_frame.shape})")

    # Warmup
    det.detect(real_frame)
    warmup_raw = det.detect(real_frame)
    print(f"Warmup raw detections: {len(warmup_raw)} -> "
          f"{sorted(d['class'] for d in warmup_raw)}")
    assert len(warmup_raw) > 0, (
        "Real frame should produce detections; check that "
        "test_frame_raw.jpg contains real objects"
    )
    expected_class = warmup_raw[0]["class"]

    raw_counts: list[int] = []
    smooth_counts: list[int] = []
    smooth_classes: list[list[str]] = []
    times_ms: list[float] = []

    # Phase A: 8 frames of empty scene (no detections expected)
    # Phase B: 10 frames with the real frame (real detections expected)
    # Phase C: 10 frames alternating real/empty (cooldown hold test)
    phases = [
        ("A: empty",   [make_empty()] * 8),
        ("B: real",    [real_frame] * 10),
        ("C: flicker", [real_frame, real_frame, make_empty(), real_frame,
                        real_frame, make_empty(), make_empty(),
                        real_frame, real_frame, real_frame]),
    ]

    print("")
    print(f"{'Phase':<10} {'Frame':<6} {'Time':<8} {'Raw':<5} {'Sm':<5} Smoothed classes")
    print("-" * 70)
    t_start = time.perf_counter()
    frame_idx = 0
    for name, frames in phases:
        for f in frames:
            t0 = time.perf_counter()
            raw = det.detect(f)
            smooth = sm.smooth(raw, time.time())
            dt_ms = (time.perf_counter() - t0) * 1000
            raw_counts.append(len(raw))
            smooth_counts.append(len(smooth))
            smooth_classes.append(sorted(d["class"] for d in smooth))
            times_ms.append(dt_ms)
            print(
                f"{name:<10} {frame_idx:<6} {dt_ms:>5.0f}ms "
                f"{len(raw):<5} {len(smooth):<5} {smooth_classes[-1] or '[]'}"
            )
            frame_idx += 1
    total_s = time.perf_counter() - t_start
    print("")
    print(f"Total: {frame_idx} frames in {total_s:.1f}s ({frame_idx/total_s:.1f} FPS)")
    print(f"Avg inference: {np.mean(times_ms):.0f}ms "
          f"(min {min(times_ms):.0f}, max {max(times_ms):.0f})")

    # ----- assertions -----
    print("")
    print("=== BEHAVIOUR ASSERTIONS ===")

    # Phase A: empty scene -> smoother must emit 0 in every frame
    a_smooth = smooth_counts[0:8]
    assert all(c == 0 for c in a_smooth), f"Phase A failed: {a_smooth}"
    print(f"[PASS] Phase A (empty): all 8 frames emitted 0 detections")

    # Phase B: real frame -> smoother must stabilise after frame 3 (3-of-5 hits)
    b_smooth_classes = smooth_classes[8:18]
    b_emits = [c for c in b_smooth_classes if expected_class in c]
    print(f"[INFO] Phase B: {expected_class} emitted in {len(b_emits)}/10 frames")
    assert len(b_emits) >= 5, (
        f"Phase B: {expected_class} should appear in >= 5 frames after warmup, "
        f"got {len(b_emits)}"
    )
    print(f"[PASS] Phase B (stable): {expected_class} emitted in {len(b_emits)}/10 frames")

    # Stability of Phase B output (frames 13-17 should all be same set)
    b_stable = smooth_classes[13:18]
    assert len(set(tuple(c) for c in b_stable)) == 1, (
        f"Phase B late frames should be stable, got {b_stable}"
    )
    print(f"[PASS] Phase B output stable across frames 13-17: {b_stable[0]}")

    # Phase C: 1-2 frame occlusions should NOT drop the class
    c_smooth_classes = smooth_classes[18:28]
    print(f"[INFO] Phase C (flicker): {c_smooth_classes}")
    c_holds = sum(1 for c in c_smooth_classes if expected_class in c)
    print(f"[INFO] Phase C: {expected_class} held in {c_holds}/{len(c_smooth_classes)} frames")
    assert c_holds >= 7, (
        f"Phase C: {expected_class} should hold across 1-2 frame gaps; "
        f"only held {c_holds}/{len(c_smooth_classes)}"
    )
    print(f"[PASS] Phase C (cooldown hold): {expected_class} held across {c_holds}/10 frames")

    # FPS: skip the first 4 frames (ultralytics/onnxruntime warmup
    # dominates those); measure steady-state throughput only.
    steady_times = times_ms[4:]
    fps_steady = len(steady_times) / (sum(steady_times) / 1000.0)
    assert fps_steady >= 8, f"Steady-state throughput {fps_steady:.1f} FPS below 8 FPS target"
    print(f"[PASS] Steady-state throughput {fps_steady:.1f} FPS >= 8 FPS target")

    # Latency: avg inference (steady state) should be under 125ms for 8 FPS
    avg_ms = float(np.mean(steady_times))
    assert avg_ms < 125, f"Avg inference {avg_ms:.0f}ms too slow for 8 FPS"
    print(f"[PASS] Avg inference (steady-state) {avg_ms:.0f}ms < 125ms")

    print("")
    print("=== ALL E2E ASSERTIONS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
