"""FastAPI application entrypoint for AeroGraph.

Phase 0: minimal scaffold with /health endpoint.
Routers for session / stream / diff / query will be wired in later phases.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from backend.api.stream import router as stream_router
from backend.api.safety import router as safety_router

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

# CORS for local front-end dev (v0, Figma, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    # --- Safety subsystem: store + notifier bus + monitor -----------------
    try:
        from backend.config import SAFETY_DIR, TELEGRAM_BOT_TOKEN, TWILIO_FROM, TWILIO_SID, TWILIO_TOKEN
        from backend.pipeline.safety_store import SafetyStore
        from backend.notifiers.notifier_bus import NotifierBus
        from backend.pipeline.safety_monitor import SafetyMonitor

        store = SafetyStore(safety_dir=SAFETY_DIR)
        registry.safety_store = store

        bus = NotifierBus()
        registry.notifier_bus = bus
        runtime.notifier_bus_ready = True
        runtime.telegram_enabled = bool(TELEGRAM_BOT_TOKEN)
        runtime.twilio_enabled = bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)
        # WhatsApp is "enabled" if the bridge URL is reachable; we don't
        # ping it at startup to avoid boot delays — it self-reports per
        # contact at escalation time.
        runtime.whatsapp_enabled = True

        # Helpers that the monitor uses. All closures so they re-read
        # live state at call time rather than capturing stale values.
        def _active_location() -> str:
            sg = registry.spatial_graph
            sid_obj = registry.camera_stream
            if sid_obj is not None:
                sid = sid_obj._session_id  # type: ignore[attr-defined]
                if sid and sg is not None:
                    m = sg.get_manifest(sid)
                    if m:
                        return m.get("location_name", "") or ""
            return ""

        def _active_session_id() -> str:
            sid_obj = registry.camera_stream
            return sid_obj._session_id if sid_obj is not None else ""  # type: ignore[attr-defined]

        def _get_last_keyframes() -> list:
            # Defer CLIP/keyframe fetch to the lazy index; if not loaded,
            # fall back to the latest frame from the camera stream.
            kfi = registry.keyframe_index
            if kfi is not None:
                try:
                    recent = kfi.get_recent_keyframes(_active_session_id(), n=3)
                    # keyframe_index stores RGB arrays; we'd need to fetch
                    # the actual frame bytes. For the hackathon we send the
                    # latest frame from CameraStream in triplicate if no
                    # other keyframes exist.
                    if recent:
                        return []  # let it fall through to the camera route
                except Exception:
                    logger.debug("safety: get_recent_keyframes failed", exc_info=True)
            cam = registry.camera_stream
            if cam is not None and cam._latest_frame is not None:
                return [cam._latest_frame.copy()]
            return []

        # STT hook — re-uses the existing Groq/local whisper path.
        def _stt_transcribe(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
            try:
                from backend.pipeline.stt_engine import transcribe_audio_bytes
                return transcribe_audio_bytes(audio_bytes, mime_type=mime_type)
            except Exception:
                return ""

        # TTS hook — uses existing pyttsx3 path with fire-and-forget.
        def _tts_speak(text: str) -> None:
            try:
                from backend.pipeline.tts_engine import speak_async
                speak_async(text)
            except Exception:
                logger.exception("safety: TTS speak_async failed")

        monitor = SafetyMonitor(
            store=store,
            notifier_bus=bus,
            tts_speak=_tts_speak,
            stt_transcribe=_stt_transcribe,
            get_keyframes=_get_last_keyframes,
            active_location=_active_location,
            active_session_id=_active_session_id,
            user_name="user",
        )
        registry.safety_monitor = monitor
        runtime.safety_monitor_ready = True
        logger.info("Safety monitor ready (state=monitoring)")
    except Exception:
        logger.exception("Failed to init safety subsystem; safety API will be degraded.")
        runtime.safety_monitor_ready = False


# Capture the asyncio loop so the monitor can schedule notifier tasks
@app.on_event("startup")
async def _capture_loop() -> None:
    """Grab the running event loop and hand it to the safety monitor so its
    confirmation worker thread can run_coroutine_threadsafe(notifier_bus.send_all).
    """
    import asyncio
    if registry.safety_monitor is not None:
        registry.safety_monitor.set_event_loop(asyncio.get_running_loop())


# Routers
app.include_router(session_router)
app.include_router(diff_router)
app.include_router(query_router)
app.include_router(stream_router)
app.include_router(safety_router)


@app.get("/health")
def health() -> dict[str, object]:
    """Service health check."""
    return {
        "status": "ok",
        "yolo_loaded": runtime.yolo_loaded,
        "chroma_ready": runtime.chroma_ready,
        "clip_loaded": runtime.clip_loaded,
        "spatial_graph_ready": runtime.spatial_graph_ready,
        "camera_streaming": runtime.camera_streaming,
        "safety_monitor_ready": runtime.safety_monitor_ready,
        "notifier_bus_ready": runtime.notifier_bus_ready,
        "telegram_enabled": runtime.telegram_enabled,
        "whatsapp_enabled": runtime.whatsapp_enabled,
        "twilio_enabled": runtime.twilio_enabled,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "AeroGraph",
        "docs": "/docs",
        "health": "/health",
    }
