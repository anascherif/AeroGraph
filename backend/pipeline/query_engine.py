"""Query engine — the brain of AeroGraph.

Ties together spatial graph, keyframe index, LLM, and diff engine
to answer user questions about their environment.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.pipeline import registry
from backend.pipeline.llm_client import ask as llm_ask, ask_stream as llm_ask_stream
from backend.pipeline.temporal_diff import TemporalDiff
from backend.config import object_category

logger = logging.getLogger("aerograph.query_engine")


class QueryEngine:
    """Orchestrate memory retrieval + LLM reasoning to answer user queries."""

    def __init__(self, keyframe_index: Any = None) -> None:
        self._kf_index = keyframe_index
        self._diff_engine: Optional[TemporalDiff] = None

    @property
    def diff_engine(self) -> TemporalDiff:
        if self._diff_engine is None:
            self._diff_engine = TemporalDiff(registry.spatial_graph)
        return self._diff_engine

    def _build_context(
        self,
        session_id: str,
        location_name: str = "",
        question: str = "",
    ) -> str:
        """Gather all spatial memory relevant to the question."""
        sg = registry.spatial_graph
        parts: list[str] = []

        # 1. Current session objects
        current = sg.get_manifest(session_id)
        if current:
            objects = sg.get_objects(session_id)
            if objects:
                lines = []
                for obj in objects:
                    co = obj.get("co_occurred_with", [])
                    cat = object_category(obj["class"])
                    lines.append(f"- {obj['class']} ({cat}): seen {obj.get('total_frames', 0)} frames, near {', '.join(co) if co else 'nothing'}")
                parts.append("Current scene objects:\n" + "\n".join(lines))

        # 2. Location-based diff (if we have a prior session)
        if location_name:
            try:
                result = self.diff_engine.compare_by_location(location_name, session_id)
                if result:
                    changes = result.get("changes", [])
                    non_unchanged = [c for c in changes if c["status"] != "unchanged"]
                    if non_unchanged:
                        lines = []
                        for c in non_unchanged:
                            lines.append(f"- {c['object']} ({c['status']}): {c['note']}")
                        parts.append("Changes since last visit:\n" + "\n".join(lines))
                    unchanged = [c for c in changes if c["status"] == "unchanged"]
                    if unchanged:
                        names = [c["object"] for c in unchanged]
                        parts.append("Objects that haven't moved: " + ", ".join(names))
            except Exception:
                logger.warning("Failed to build diff context", exc_info=True)

        # 3. Keyframe visual similarity (if we have a question about "what changed")
        if self._kf_index and question and any(w in question.lower() for w in ("change", "different", "moved", "missing", "new")):
            recent = self._kf_index.get_recent_keyframes(session_id, n=3)
            if recent:
                parts.append(f"Recent visual snapshots: {len(recent)} keyframes from this session")

        # 4. Session metadata
        if current:
            start = current.get("started_at", "")
            if isinstance(start, (int, float)):
                import time as _time
                start = _time.strftime("%H:%M", _time.localtime(start))
            parts.append(f"Current session started at {start}, location: {location_name or current.get('location_name', 'unknown')}")

        return "\n\n".join(parts) if parts else "No spatial memory data available yet."

    def answer(
        self,
        question: str,
        *,
        session_id: str = "",
        location_name: str = "",
    ) -> str:
        """Answer a text question using all available memory."""
        if not session_id:
            return "No active session. Please start a session first."

        context = self._build_context(session_id, location_name, question)
        logger.info("Query context:\n%s", context[:500])
        response = llm_ask(question, context=context)
        return response

    def answer_stream(
        self,
        question: str,
        *,
        session_id: str = "",
        location_name: str = "",
    ):
        """Yield answer tokens as they stream from the LLM."""
        if not session_id:
            yield "No active session. Please start a session first."
            return

        context = self._build_context(session_id, location_name, question)
        yield from llm_ask_stream(question, context=context)

    def search_visually(
        self,
        query_text: str,
        *,
        location_name: str = "",
        n_results: int = 5,
    ) -> list[dict]:
        """Search the keyframe index by text description."""
        if not self._kf_index:
            return []
        return self._kf_index.search_by_text(
            query_text, location_name=location_name, n_results=n_results
        )
