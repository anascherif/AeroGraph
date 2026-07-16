"""Stage 3 — Temporal Difference Engine for AeroGraph.

Compares two sessions at the same location (a "reference" — last visit, and
"current" — this visit) and produces a structured list of changes:

  * ``unchanged``       — object present in both, same neighbourhood
  * ``moved``           — same object, but centroid shifted enough to matter
  * ``missing``         — was there last time, gone now
  * ``new``             — appeared since last visit (flagged as hazard if the
                          class is a navigation obstacle)
  * ``context_changed``  — still there, but the objects around it changed
                          (e.g. "the table is there but the keys on it are gone")

Each change carries a human-readable ``note`` that feeds directly into the
Phase 4 LLM answer generation.

Because the camera moves with the user, the "moved" status relies on a
co-occurrence similarity heuristic: we only trust centroid shifts when the
neighbouring object set is similar between the two sessions (same camera
viewpoint).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from backend.config import (
    CENTROID_SHIFT_THRESHOLD,
    PIXELS_PER_METER,
    object_category,
)
from backend.pipeline.spatial_graph import SpatialGraph

logger = logging.getLogger("aerograph.temporal_diff")


# Status constants — kept as plain strings for JSON friendliness
UNCHANGED = "unchanged"
MOVED = "moved"
MISSING = "missing"
NEW = "new"
CONTEXT_CHANGED = "context_changed"

# Co-occurrence overlap required to trust a centroid shift as "moved".
# We only require *one* common neighbor (same neighbourhood / camera angle),
# not a majority overlap — the camera viewpoint is close enough as long as
# at least one surrounding object is shared.
_CO_OCCURRENCE_TRUST = 0.0  # disabled; we use a shared-neighbor check instead


class TemporalDiff:
    """Compare two session manifests and compute the list of changes."""

    def __init__(self, spatial_graph: SpatialGraph) -> None:
        self.sg = spatial_graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compare(
        self,
        reference_session_id: str,
        current_session_id: str,
    ) -> Optional[dict[str, Any]]:
        """Compare two sessions and return a structured diff.

        Returns ``None`` if either session does not exist.
        """
        ref = self.sg.get_manifest(reference_session_id)
        cur = self.sg.get_manifest(current_session_id)
        if ref is None or cur is None:
            return None

        ref_objs = self._indexed_objects(reference_session_id)
        cur_objs = self._indexed_objects(current_session_id)

        ref_classes = set(ref_objs.keys())
        cur_classes = set(cur_objs.keys())

        changes: list[dict[str, Any]] = []

        # --- objects present in both sessions ---
        for cls in sorted(ref_classes & cur_classes):
            r = ref_objs[cls]
            c = cur_objs[cls]
            change = self._diff_same_class(cls, r, c)
            changes.append(change)

        # --- objects only in reference (missing) ---
        for cls in sorted(ref_classes - cur_classes):
            r = ref_objs[cls]
            changes.append(self._missing_change(cls, r))

        # --- objects only in current (new) ---
        for cls in sorted(cur_classes - ref_classes):
            c = cur_objs[cls]
            changes.append(self._new_change(cls, c))

        # Sort: hazards first, then missing, then moved, then the rest
        status_order = {
            NEW: 0,
            MISSING: 1,
            MOVED: 2,
            CONTEXT_CHANGED: 3,
            UNCHANGED: 4,
        }
        changes.sort(key=lambda ch: (status_order.get(ch["status"], 9), ch["object"]))

        # --- summary counts ---
        summary = {s: 0 for s in [UNCHANGED, MOVED, MISSING, NEW, CONTEXT_CHANGED]}
        for ch in changes:
            summary[ch["status"]] += 1

        return {
            "reference_session": self.sg._summary(ref),
            "current_session": self.sg._summary(cur),
            "location_name": ref.get("location_name") or cur.get("location_name"),
            "changes": changes,
            "summary": summary,
        }

    def compare_by_location(
        self,
        location_name: str,
        current_session_id: str,
    ) -> Optional[dict[str, Any]]:
        """Auto-find the most recent *previous* session at ``location_name``
        and diff it against ``current_session_id``.

        Returns ``None`` if no previous session exists at that location
        or the current session doesn't exist.
        """
        cur = self.sg.get_manifest(current_session_id)
        if cur is None:
            return None

        sessions = self.sg.list_sessions()
        # candidates: same location, stopped, NOT the current session
        candidates = [
            s for s in sessions
            if s["location_name"] == location_name
            and s["session_id"] != current_session_id
            and s["stopped_at"] is not None
        ]
        if not candidates:
            return None
        # most recent previous session
        candidates.sort(key=lambda s: s["started_at"], reverse=True)
        ref_id = candidates[0]["session_id"]
        return self.compare(ref_id, current_session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _diff_same_class(
        self,
        cls: str,
        ref: dict[str, Any],
        cur: dict[str, Any],
    ) -> dict[str, Any]:
        cat = object_category(cls)
        co_before = set(ref.get("co_occurred_with", []))
        co_after = set(cur.get("co_occurred_with", []))

        # Co-occurrence Jaccard similarity
        union = co_before | co_after
        if union:
            jaccard = len(co_before & co_after) / len(union)
        else:
            jaccard = 1.0

        # Context changed?
        context_changed = co_before != co_after and co_before and co_after

        # Centroid shift (normalised 0-1)
        rc = ref.get("last_centroid", [0, 0])
        cc = cur.get("last_centroid", [0, 0])
        ref_w = ref.get("frame_w") or 640
        ref_h = ref.get("frame_h") or 480
        cur_w = cur.get("frame_w") or 640
        cur_h = cur.get("frame_h") or 480
        # normalise both to [0,1] so frames of different size are comparable
        rnx = rc[0] / ref_w if ref_w else 0
        rny = rc[1] / ref_h if ref_h else 0
        cnx = cc[0] / cur_w if cur_w else 0
        cny = cc[1] / cur_h if cur_h else 0
        shift = math.hypot(cnx - rnx, cny - rny)

        # Trust the centroid shift only if at least one neighbor is shared
        # (same camera angle / neighbourhood). With no shared neighbors we
        # treat it as too unreliable on a moving camera.
        shared_neighbors = bool(co_before & co_after)

        moved = shift >= CENTROID_SHIFT_THRESHOLD and shared_neighbors

        if moved:
            displacement_m = round(shift * PIXELS_PER_METER / 100.0, 2)
            direction = self._direction(rnx, rny, cnx, cny)
            note = self._moved_note(cls, displacement_m, direction, cat)
            return {
                "object": cls,
                "status": MOVED,
                "category": cat,
                "displacement_m": displacement_m,
                "direction": direction,
                "co_occurrence_before": sorted(co_before),
                "co_occurrence_after": sorted(co_after),
                "note": note,
            }

        if context_changed:
            lost = sorted(co_before - co_after)
            gained = sorted(co_after - co_before)
            note = self._context_note(cls, lost, gained, cat)
            return {
                "object": cls,
                "status": CONTEXT_CHANGED,
                "category": cat,
                "co_occurrence_before": sorted(co_before),
                "co_occurrence_after": sorted(co_after),
                "gained_neighbors": gained,
                "lost_neighbors": lost,
                "note": note,
            }

        note = self._unchanged_note(cls, cat)
        return {
            "object": cls,
            "status": UNCHANGED,
            "category": cat,
            "co_occurrence_before": sorted(co_before),
            "co_occurrence_after": sorted(co_after),
            "note": note,
        }

    def _missing_change(self, cls: str, ref: dict[str, Any]) -> dict[str, Any]:
        cat = object_category(cls)
        co = sorted(ref.get("co_occurred_with", []))
        note = self._missing_note(cls, co, cat)
        return {
            "object": cls,
            "status": MISSING,
            "category": cat,
            "co_occurrence_before": co,
            "co_occurrence_after": [],
            "note": note,
        }

    def _new_change(self, cls: str, cur: dict[str, Any]) -> dict[str, Any]:
        cat = object_category(cls)
        co = sorted(cur.get("co_occurred_with", []))
        note = self._new_note(cls, co, cat)
        return {
            "object": cls,
            "status": NEW,
            "category": cat,
            "co_occurrence_before": [],
            "co_occurrence_after": co,
            "note": note,
        }

    # ------------------------------------------------------------------
    # Note generators (human-readable strings for the LLM / TTS in Phase 4)
    # ------------------------------------------------------------------
    @staticmethod
    def _direction(
        rnx: float, rny: float, cnx: float, cny: float
    ) -> str:
        dx = cnx - rnx  # +ve = moved right
        dy = cny - rny  # +ve = moved down (further away in frame)
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            return "in_place"
        # Pick the dominant axis
        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        # Vertical: in a walkthrough, lower y = further, higher y = closer
        return "further" if dy < 0 else "closer"

    @staticmethod
    def _moved_note(cls: str, dist: float, direction: str, cat: str) -> str:
        dir_text = {
            "left": "to your left",
            "right": "to your right",
            "closer": "closer to you",
            "further": "further away",
            "in_place": "slightly",
        }.get(direction, direction)
        return f"The {cls} moved about {dist} meters {dir_text}."

    @staticmethod
    def _context_note(
        cls: str, lost: list[str], gained: list[str], cat: str
    ) -> str:
        parts = [f"The {cls} is still there"]
        if lost:
            parts.append(f"but the {', '.join(lost)} near it {'are' if len(lost)>1 else 'is'} gone")
        if gained:
            if lost:
                parts.append("and")
            else:
                parts.append("but")
            parts.append(f"a new {', '.join(gained)} appeared nearby")
        return " ".join(parts) + "."

    @staticmethod
    def _missing_note(cls: str, co: list[str], cat: str) -> str:
        if co:
            neighbor_text = f" near the {', '.join(co)}"
        else:
            neighbor_text = ""
        return f"Your {cls} was{neighbor_text} last time, but it's not there now."

    @staticmethod
    def _new_note(cls: str, co: list[str], cat: str) -> str:
        if cat == "hazard":
            prefix = f"A new {cls} appeared"
            if co:
                prefix += f" near the {', '.join(co)}"
            return prefix + " — possible hazard, watch your step."
        if co:
            return f"A {cls} appeared near the {', '.join(co)}."
        return f"A {cls} appeared in this area."

    @staticmethod
    def _unchanged_note(cls: str, cat: str) -> str:
        return f"The {cls} is still there."

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _indexed_objects(self, session_id: str) -> dict[str, dict[str, Any]]:
        """Return ``{class_name: object_dict}`` for a session's deduped objects."""
        objs = self.sg.get_objects(session_id)
        return {o["class"]: o for o in objs if "class" in o}
