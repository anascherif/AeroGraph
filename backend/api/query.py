"""Query API — the main user-facing endpoint for AeroGraph.

POST /v1/query           — answer a text question
POST /v1/query/voice     — answer a voice question (audio upload)
POST /v1/query/speak     — answer + speak aloud (text in, audio out)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from backend.pipeline import registry
from backend.pipeline.query_engine import QueryEngine

logger = logging.getLogger("aerograph.api.query")

router = APIRouter(prefix="/v1/query", tags=["query"])

_query_engine: Optional[QueryEngine] = None


def _get_keyframe_index():
    """Lazy-load the CLIP keyframe index (blocks on first call while model loads)."""
    if registry.keyframe_index is None:
        from backend.config import CHROMA_PATH, runtime
        from backend.pipeline.keyframe_index import KeyframeIndex
        logger.info("Lazy-loading CLIP keyframe index (first query)...")
        t0 = time.perf_counter()
        try:
            registry.keyframe_index = KeyframeIndex(chroma_path=CHROMA_PATH)
            runtime.clip_loaded = True
            logger.info("CLIP + ChromaDB ready in %.2fs", time.perf_counter() - t0)
        except Exception:
            logger.exception("Failed to load CLIP; visual search will be unavailable.")
            raise HTTPException(status_code=503, detail="CLIP model not available")
    return registry.keyframe_index


def _get_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        # Create engine without CLIP — spatial graph + LLM only
        _query_engine = QueryEngine()
    return _query_engine


class TextQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    session_id: str = Field(default="")
    location_name: str = Field(default="")


class TextQueryResponse(BaseModel):
    answer: str
    session_id: str
    location_name: str


class VoiceQueryResponse(BaseModel):
    answer: str
    transcription: str
    session_id: str


@router.post("", response_model=TextQueryResponse)
def query_text(req: TextQueryRequest) -> TextQueryResponse:
    """Answer a text question about the user's environment."""
    engine = _get_engine()

    session_id = req.session_id
    if not session_id:
        sg = registry.spatial_graph
        sessions = sg.list_sessions()
        if sessions:
            session_id = sessions[0]["session_id"]
        else:
            raise HTTPException(status_code=400, detail="No active session. Start one first.")

    try:
        answer = engine.answer(
            req.question,
            session_id=session_id,
            location_name=req.location_name,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return TextQueryResponse(
        answer=answer,
        session_id=session_id,
        location_name=req.location_name,
    )


@router.post("/voice", response_model=VoiceQueryResponse)
async def query_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(default=""),
    location_name: str = Form(default=""),
) -> VoiceQueryResponse:
    """Answer a voice question.  Uploads audio, transcribes, then answers."""
    from backend.pipeline.stt_engine import transcribe_audio_bytes

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    transcription = transcribe_audio_bytes(audio_bytes, mime_type=audio.content_type or "audio/webm")
    if not transcription:
        raise HTTPException(status_code=422, detail="Could not transcribe the audio")

    engine = _get_engine()

    if not session_id:
        sg = registry.spatial_graph
        sessions = sg.list_sessions()
        if sessions:
            session_id = sessions[0]["session_id"]
        else:
            raise HTTPException(status_code=400, detail="No active session")

    answer = engine.answer(
        transcription,
        session_id=session_id,
        location_name=location_name,
    )
    return VoiceQueryResponse(
        answer=answer,
        transcription=transcription,
        session_id=session_id,
    )


@router.post("/speak")
async def query_speak(
    audio: UploadFile = File(...),
    session_id: str = Form(default=""),
    location_name: str = Form(default=""),
) -> dict:
    """Answer a voice question and speak the answer aloud."""
    from backend.pipeline.stt_engine import transcribe_audio_bytes
    from backend.pipeline.tts_engine import speak_async

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    transcription = transcribe_audio_bytes(audio_bytes, mime_type=audio.content_type or "audio/webm")
    if not transcription:
        raise HTTPException(status_code=422, detail="Could not transcribe the audio")

    engine = _get_engine()

    if not session_id:
        sg = registry.spatial_graph
        sessions = sg.list_sessions()
        if sessions:
            session_id = sessions[0]["session_id"]
        else:
            raise HTTPException(status_code=400, detail="No active session")

    answer = engine.answer(
        transcription,
        session_id=session_id,
        location_name=location_name,
    )

    # Speak in background (non-blocking)
    speak_async(answer)

    return {
        "answer": answer,
        "transcription": transcription,
        "session_id": session_id,
        "spoken": True,
    }


class VisualSearchRequest(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=200)
    location_name: str = Field(default="")
    n_results: int = Field(default=5, ge=1, le=20)


@router.post("/visual_search")
def visual_search(req: VisualSearchRequest) -> dict:
    """Search the keyframe index by text description."""
    if registry.keyframe_index is None:
        return {
            "query": req.query_text,
            "results": [],
            "total": 0,
            "error": "CLIP model not loaded yet. It will load on first use.",
        }
    results = registry.keyframe_index.search_by_text(
        req.query_text, location_name=req.location_name, n_results=req.n_results
    )
    return {
        "query": req.query_text,
        "results": results,
        "total": len(results),
    }
