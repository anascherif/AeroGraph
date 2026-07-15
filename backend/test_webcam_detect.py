"""Quick webcam test for the AeroGraph detector.

Grabs a single frame from the default webcam, runs the YOLO11n detector on it,
prints the filtered detections, and saves the annotated frame to disk for
manual inspection.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2

from backend.config import MODELS_DIR, DETECTION_CLASSES, DETECTION_CONFIDENCE
from backend.pipeline.detector import Detector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("aerograph.test")


def main() -> None:
    onnx_path = MODELS_DIR / "yolo11n.onnx"
    if not onnx_path.exists():
        raise SystemExit(
            f"ONNX model not found at {onnx_path}. "
            "Run: python -m backend.pipeline.export_model"
        )

    logger.info("Opening webcam (index 0) ...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit("Could not open webcam.")

    # Warm up the camera (first few frames are often dark)
    for _ in range(15):
        cap.read()
        time.sleep(0.05)

    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise SystemExit("Failed to grab frame from webcam.")
    logger.info("Frame grabbed: shape=%s dtype=%s", frame.shape, frame.dtype)

    detector = Detector(
        model_path=str(onnx_path),
        allowed_classes=DETECTION_CLASSES,
        confidence=DETECTION_CONFIDENCE,
    )

    t0 = time.perf_counter()
    detections = detector.detect(frame)
    dt = time.perf_counter() - t0
    logger.info("Inference took %.3fs, %d detection(s) after filtering", dt, len(detections))

    print("\n" + "=" * 60)
    print(f"  {len(detections)} detection(s) in {dt:.3f}s")
    print("=" * 60)
    for i, d in enumerate(detections):
        print(
            f"  [{i}] {d['class']:<14} conf={d['confidence']:.2f}  "
            f"bbox={d['bbox']}  centroid={d['centroid']}"
        )
    print("=" * 60 + "\n")

    # Save an annotated copy for visual inspection
    out_path = Path("data/test_frame_raw.jpg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)

    annotated = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        cx, cy = d["centroid"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(annotated, (cx, cy), 4, (0, 0, 255), -1)
        label = f"{d['class']} {d['confidence']:.2f}"
        cv2.putText(
            annotated,
            label,
            (x1, max(y1 - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
        )
    annot_path = Path("data/test_frame_annotated.jpg")
    cv2.imwrite(str(annot_path), annotated)
    logger.info("Saved raw frame to       %s", out_path.resolve())
    logger.info("Saved annotated frame to %s", annot_path.resolve())


if __name__ == "__main__":
    main()
