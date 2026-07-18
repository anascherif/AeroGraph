"""Keyframe index for AeroGraph — CLIP embeddings stored in ChromaDB.

Captures visual snapshots ("keyframes"), encodes them with CLIP, and stores
them in a vector database so the query layer can retrieve visually similar
past scenes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import chromadb
import numpy as np
import open_clip
import torch
from PIL import Image

from backend.config import CHROMA_PATH, KEYFRAME_INTERVAL_S

logger = logging.getLogger("aerograph.keyframe_index")

COLLECTION_NAME = "keyframes"


class KeyframeIndex:
    """Thin wrapper around CLIP + ChromaDB for visual memory retrieval."""

    def __init__(self, chroma_path: Path = CHROMA_PATH) -> None:
        self._chroma_path = chroma_path
        self._chroma_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB — persistent, local
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # CLIP model (CPU only)
        logger.info("Loading CLIP model (RN50)...")
        t0 = time.perf_counter()
        self._device = "cpu"
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            "RN50", pretrained="openai", device=self._device
        )
        self._tokenizer = open_clip.get_tokenizer("RN50")
        self._model.eval()
        logger.info("CLIP model loaded in %.2fs", time.perf_counter() - t0)

        # Throttle keyframe capture — don't re-encode every frame
        self._last_capture_ts: dict[str, float] = {}

    def encode_image(self, frame_rgb: np.ndarray) -> np.ndarray:
        """Encode a single RGB frame (H, W, 3 uint8) into a CLIP embedding."""
        img = Image.fromarray(frame_rgb)
        tensor = self._preprocess(img).unsqueeze(0).to(self._device)
        with torch.no_grad():
            emb = self._model.encode_image(tensor)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.cpu().numpy().flatten()

    def encode_text(self, text: str) -> np.ndarray:
        """Encode a text query into the CLIP embedding space."""
        tokens = self._tokenizer([text]).to(self._device)
        with torch.no_grad():
            emb = self._model.encode_text(tokens)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.cpu().numpy().flatten()

    def add_keyframe(
        self,
        frame_rgb: np.ndarray,
        *,
        session_id: str,
        location_name: str = "",
        objects: list[str] | None = None,
        timestamp: float | None = None,
    ) -> str:
        """Encode and store a keyframe.  Returns the keyframe ID.

        Throttles to at most one keyframe per session per
        ``KEYFRAME_INTERVAL_S`` to avoid flooding the database.
        """
        ts = timestamp or time.time()
        last = self._last_capture_ts.get(session_id, 0.0)
        if ts - last < KEYFRAME_INTERVAL_S:
            return ""  # too soon

        self._last_capture_ts[session_id] = ts
        emb = self.encode_image(frame_rgb)

        kf_id = f"kf_{session_id}_{int(ts * 1000)}"
        meta = {
            "session_id": session_id,
            "location_name": location_name,
            "timestamp": ts,
            "objects": ",".join(objects or []),
        }

        self._collection.add(
            ids=[kf_id],
            embeddings=[emb.tolist()],
            metadatas=[meta],
        )
        logger.debug("Keyframe stored: %s (objects=%s)", kf_id, objects)
        return kf_id

    def search_by_image(
        self,
        frame_rgb: np.ndarray,
        *,
        n_results: int = 5,
        location_filter: str = "",
    ) -> list[dict]:
        """Find visually similar past keyframes."""
        emb = self.encode_image(frame_rgb)
        where = (
            {"location_name": location_filter}
            if location_filter
            else None
        )
        results = self._collection.query(
            query_embeddings=[emb.tolist()],
            n_results=n_results,
            where=where,
        )
        return self._format_results(results)

    def search_by_text(
        self,
        text: str,
        *,
        n_results: int = 5,
        location_name: str = "",
    ) -> list[dict]:
        """Find keyframes matching a text description."""
        emb = self.encode_text(text)
        where = (
            {"location_name": location_name}
            if location_name
            else None
        )
        results = self._collection.query(
            query_embeddings=[emb.tolist()],
            n_results=n_results,
            where=where,
        )
        return self._format_results(results)

    def get_recent_keyframes(
        self,
        session_id: str,
        n: int = 5,
    ) -> list[dict]:
        """Return the most recent keyframes for a session."""
        results = self._collection.get(
            where={"session_id": session_id},
            include=["metadatas"],  # don't fetch embeddings
        )
        items = []
        for i, kf_id in enumerate(results["ids"]):
            items.append(
                {
                    "id": kf_id,
                    "metadata": results["metadatas"][i],
                }
            )
        # Sort by timestamp descending
        items.sort(key=lambda x: x["metadata"].get("timestamp", 0), reverse=True)
        return items[:n]

    def count(self) -> int:
        return self._collection.count()

    @staticmethod
    def _format_results(results: dict) -> list[dict]:
        formatted = []
        if not results["ids"] or not results["ids"][0]:
            return formatted
        for i, kf_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            formatted.append(
                {
                    "id": kf_id,
                    "metadata": meta,
                    "distance": dist,
                }
            )
        return formatted
