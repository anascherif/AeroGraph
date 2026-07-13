"""FastAPI application entrypoint for AeroGraph.

Phase 0: minimal scaffold with /health endpoint.
Routers for session / stream / diff / query will be wired in later phases.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from backend.config import runtime, ensure_dirs, CHROMA_PATH, MODELS_DIR

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
    # YOLO / ChromaDB / CLIP will be initialised lazily in later phases.
    runtime.chroma_ready = CHROMA_PATH.exists()


@app.get("/health")
def health() -> dict[str, object]:
    """Service health check."""
    return {
        "status": "ok",
        "yolo_loaded": runtime.yolo_loaded,
        "chroma_ready": runtime.chroma_ready,
        "clip_loaded": runtime.clip_loaded,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "AeroGraph",
        "docs": "/docs",
        "health": "/health",
    }
