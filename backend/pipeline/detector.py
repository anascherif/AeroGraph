"""YOLO11n ONNX inference wrapper for AeroGraph Stage 1.

Loads an exported YOLO11n ONNX model via the ultralytics `YOLO()` backend
(which uses onnxruntime under the hood and handles preprocessing, NMS, and
coordinate mapping correctly), filters detections to navigation-relevant
COCO classes, and returns structured results suitable for the spatial
graph and temporal diff stages.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from ultralytics import YOLO

from backend.config import YOLO_IMGSZ

logger = logging.getLogger("aerograph.detector")


class Detector:
    """Thin wrapper around ultralytics YOLO for filtered object detection.

    Parameters
    ----------
    model_path:
        Path to the exported ``yolo11n.onnx`` file.
    allowed_classes:
        List of COCO class names to keep (anything else is discarded).
    confidence:
        Minimum confidence score for a detection to be kept.
    """

    def __init__(
        self,
        model_path: str,
        allowed_classes: list[str],
        confidence: float = 0.35,
    ) -> None:
        self.model_path = model_path
        self.confidence = confidence
        # Set of allowed class indices for fast lookup
        self._allowed_names = set(allowed_classes)

        t0 = time.perf_counter()
        logger.info("Loading YOLO model from %s ...", model_path)
        self.model: YOLO = YOLO(model_path)
        # Build the class index -> name map from the loaded model
        self._names: dict[int, str] = dict(self.model.names)  # type: ignore[arg-type]
        # Precompute the set of allowed class indices for speed
        self._allowed_ids: set[int] = {
            idx for idx, name in self._names.items() if name in self._allowed_names
        }
        elapsed = time.perf_counter() - t0
        logger.info(
            "YOLO loaded in %.2fs (%d COCO classes, %d allowed)",
            elapsed,
            len(self._names),
            len(self._allowed_ids),
        )

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Run detection on a single BGR frame.

        Parameters
        ----------
        frame:
            OpenCV BGR image, shape ``(H, W, 3)``, dtype ``uint8``.

        Returns
        -------
        list of dict
            Each dict has keys:
            ``class`` (str), ``bbox`` (``[x1, y1, x2, y2]`` as ints),
            ``centroid`` (``[cx, cy]`` as ints), ``confidence`` (float).
        """
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            iou=0.45,
            device="cpu",
            verbose=False,
            imgsz=YOLO_IMGSZ,
        )
        if not results:
            return []

        r = results[0]
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            return []

        out: list[dict[str, Any]] = []
        # boxes.xyxy is (N, 4) tensor, .conf (N,), .cls (N,)
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clses = boxes.cls.cpu().numpy().astype(int)

        for i in range(len(xyxy)):
            cls_id = int(clses[i])
            if cls_id not in self._allowed_ids:
                continue
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            out.append(
                {
                    "class": self._names.get(cls_id, str(cls_id)),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "centroid": [int(cx), int(cy)],
                    "confidence": round(float(confs[i]), 3),
                }
            )
        return out

    @property
    def allowed_class_names(self) -> set[str]:
        return set(self._allowed_names)
