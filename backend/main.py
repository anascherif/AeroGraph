"""FastAPI application entrypoint for AeroGraph.

Phase 0: minimal scaffold with /health endpoint.
Routers for session / stream / diff / query will be wired in later phases.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI

from backend.config import (
    runtime,
    ensure_dirs,
    CHROMA_PATH,
    MODELS_DIR,
    SESSIONS_DIR,
    DETECTION_CLASSES,
    DETECTION_CONFIDENCE,
)
from backend.pipeline import registry
from backend.pipeline.export_model import ensure_onnx_model
from backend.api.session import router as session_router
from backend.api.diff import router as diff_router
from backend.api.query import router as query_router

logger = logging.getLogger("aerograph")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
)


app = FastAPI(
    title="AeroGraph",
    description="Spatial memory engine for visually impaired users.",
    version="0.1.0",
)


@app.on_event("startup")
def _on_startup() -> None:
    ensure_dirs()
    logger.info("Data dir ready: %s", CHROMA_PATH)
    logger.info("Models dir ready: %s", MODELS_DIR)
    logger.info("Sessions dir ready: %s", SESSIONS_DIR)
    runtime.chroma_ready = CHROMA_PATH.exists()

    # --- Initialise SpatialGraph (lightweight, JSON-backed) ---
    try:
        from backend.pipeline.spatial_graph import SpatialGraph

        registry.spatial_graph = SpatialGraph(sessions_dir=SESSIONS_DIR)
        runtime.spatial_graph_ready = True
    except Exception:
        logger.exception("Failed to init SpatialGraph; session API will be degraded.")
        runtime.spatial_graph_ready = False

    # --- Load YOLO11n detector (export onnx if needed) ---
    t0 = time.perf_counter()
    try:
        onnx_path = ensure_onnx_model("yolo11n.pt")
        from backend.pipeline.detector import Detector

        registry.detector = Detector(
            model_path=str(onnx_path),
            allowed_classes=DETECTION_CLASSES,
            confidence=DETECTION_CONFIDENCE,
        )
        runtime.yolo_loaded = True
        logger.info(
            "Detector ready in %.2fs (%d allowed classes)",
            time.perf_counter() - t0,
            len(DETECTION_CLASSES),
        )
    except Exception:
        logger.exception("Failed to load YOLO detector; pipeline will be degraded.")
        runtime.yolo_loaded = False

    # NOTE: CLIP keyframe index is lazy-loaded on first query request
    # to avoid blocking server startup with the ~2min model download.


# Routers
app.include_router(session_router)
app.include_router(diff_router)
app.include_router(query_router)


@app.get("/health")
def health() -> dict[str, object]:
    """Service health check."""
    return {
        "status": "ok",
        "yolo_loaded": runtime.yolo_loaded,
        "chroma_ready": runtime.chroma_ready,
        "clip_loaded": runtime.clip_loaded,
        "spatial_graph_ready": runtime.spatial_graph_ready,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "AeroGraph",
        "docs": "/docs",
        "health": "/health",
    }
