"""Regression test for temporal diff engine.

Verifies:
- All 5 statuses (new, missing, moved, context_changed, unchanged) are produced
- Displacement calculation is correct for same-resolution frames
- Shared-neighbor check correctly gates "moved" classification
"""

from __future__ import annotations

import math
import shutil
import tempfile
import pathlib
import time

from backend.pipeline.spatial_graph import SpatialGraph
from backend.pipeline.temporal_diff import TemporalDiff


def test_all_five_statuses() -> None:
    """Reference + current session with staged changes produces all 5 statuses."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    sg = SpatialGraph(sessions_dir=tmp)

    # Reference session (last visit)
    ref = sg.start_session("kitchen")
    ref_id = ref["session_id"]
    t = time.time()
    for i in range(20):
        sg.add_detections(ref_id, [
            {"class": "chair", "bbox": [100, 200, 250, 420], "centroid": [175, 310], "confidence": 0.9},
            {"class": "dining table", "bbox": [200, 300, 500, 460], "centroid": [350, 380], "confidence": 0.85},
            {"class": "cup", "bbox": [300, 320, 340, 360], "centroid": [320, 340], "confidence": 0.88},
        ], (480, 640), timestamp=t + i * 0.1)
    for i in range(20):
        sg.add_detections(ref_id, [
            {"class": "couch", "bbox": [50, 150, 400, 400], "centroid": [225, 275], "confidence": 0.92},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=t + 6 + i * 0.1)
    sg.stop_session(ref_id)

    # Current session (this visit)
    cur = sg.start_session("kitchen")
    cur_id = cur["session_id"]
    t2 = time.time() + 100
    for i in range(20):
        sg.add_detections(cur_id, [
            {"class": "chair", "bbox": [10, 200, 160, 420], "centroid": [85, 310], "confidence": 0.9},  # moved left
            {"class": "dining table", "bbox": [200, 300, 500, 460], "centroid": [350, 380], "confidence": 0.85},  # unchanged
            {"class": "bottle", "bbox": [310, 330, 340, 380], "centroid": [325, 355], "confidence": 0.87},  # NEW
        ], (480, 640), timestamp=t2 + i * 0.1)
    for i in range(20):
        sg.add_detections(cur_id, [
            {"class": "couch", "bbox": [50, 150, 400, 400], "centroid": [225, 275], "confidence": 0.92},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=t2 + 6 + i * 0.1)
    sg.stop_session(cur_id)

    # Diff
    td = TemporalDiff(sg)
    result = td.compare(ref_id, cur_id)

    # Verify all 5 statuses
    statuses = {ch["status"] for ch in result["changes"]}
    assert statuses == {"new", "missing", "moved", "context_changed", "unchanged"}, \
        f"Expected 5 statuses, got: {statuses}"

    # Verify specific changes
    by_obj = {ch["object"]: ch for ch in result["changes"]}

    # bottle is NEW (hazard category=hazard -> hazard note
    assert by_obj["bottle"]["status"] == "new"
    assert "hazard" in by_obj["bottle"]["note"].lower()

    # cup is MISSING
    assert by_obj["cup"]["status"] == "missing"

    # chair is MOVED with reasonable displacement
    assert by_obj["chair"]["status"] == "moved"
    assert "left" in by_obj["chair"]["direction"]  # moved left
    assert by_obj["chair"]["displacement_m"] > 0.5  # ~0.66m on 640px frame

    # dining table is CONTEXT_CHANGED (cup gone, bottle appeared)
    assert by_obj["dining table"]["status"] == "context_changed"

    # couch, tv are UNCHANGED
    assert by_obj["couch"]["status"] == "unchanged"
    assert by_obj["tv"]["status"] == "unchanged"

    shutil.rmtree(tmp)


def test_displacement_formula() -> None:
    """Displacement calculation matches pixel math for same-resolution frames."""
    from backend.config import PIXELS_PER_METER

    tmp = pathlib.Path(tempfile.mkdtemp())
    sg = SpatialGraph(sessions_dir=tmp)

    ref = sg.start_session("kitchen")
    ref_id = ref["session_id"]
    t = time.time()
    # Chair + shared anchor (tv)
    for i in range(20):
        sg.add_detections(ref_id, [
            {"class": "chair", "bbox": [100, 200, 250, 420], "centroid": [175, 310], "confidence": 0.9},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=t + i * 0.1)
    sg.stop_session(ref_id)

    cur = sg.start_session("kitchen")
    cur_id = cur["session_id"]
    t2 = time.time() + 100
    # Chair moved left 90px, tv unchanged
    for i in range(20):
        sg.add_detections(cur_id, [
            {"class": "chair", "bbox": [10, 200, 160, 420], "centroid": [85, 310], "confidence": 0.9},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=t2 + i * 0.1)
    sg.stop_session(cur_id)

    td = TemporalDiff(sg)
    result = td.compare(ref_id, cur_id)

    chair = next(ch for ch in result["changes"] if ch["object"] == "chair")
    assert chair["status"] == "moved"

    # Expected: 90px shift / 120 px/m = 0.75m
    expected_m = 90.0 / PIXELS_PER_METER
    actual_m = chair["displacement_m"]
    assert abs(actual_m - expected_m) < 0.02, \
        f"Expected ~{expected_m:.2f}m, got {actual_m}m"

    shutil.rmtree(tmp)


def test_shared_neighbor_gate() -> None:
    """Without shared neighbors, same object is NOT classified as moved."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    sg = SpatialGraph(sessions_dir=tmp)

    ref = sg.start_session("room")
    ref_id = ref["session_id"]
    t = time.time()
    for i in range(20):
        sg.add_detections(ref_id, [
            {"class": "chair", "bbox": [100, 200, 250, 420], "centroid": [175, 310], "confidence": 0.9},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=t + i * 0.1)
    sg.stop_session(ref_id)

    cur = sg.start_session("room")
    cur_id = cur["session_id"]
    t2 = time.time() + 100
    for i in range(20):
        sg.add_detections(cur_id, [
            {"class": "chair", "bbox": [10, 200, 160, 420], "centroid": [85, 310], "confidence": 0.9},
            {"class": "couch", "bbox": [50, 150, 400, 400], "centroid": [225, 275], "confidence": 0.92},
        ], (480, 640), timestamp=t2 + i * 0.1)
    sg.stop_session(cur_id)

    td = TemporalDiff(sg)
    result = td.compare(ref_id, cur_id)

    chair = next(ch for ch in result["changes"] if ch["object"] == "chair")
    # No shared neighbor (tv disappeared, couch is new) -> should be context_changed, NOT moved
    assert chair["status"] == "context_changed", \
        f"Expected context_changed due to no shared neighbor, got {chair['status']}"

    shutil.rmtree(tmp)


def test_location_autodiff() -> None:
    """compare_by_location finds the most recent previous session at same location."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    sg = SpatialGraph(sessions_dir=tmp)

    # First session at "living_room" with chair + shared anchor (tv)
    s1 = sg.start_session("living_room")
    for i in range(20):
        sg.add_detections(s1["session_id"], [
            {"class": "chair", "bbox": [100, 200, 250, 420], "centroid": [175, 310], "confidence": 0.9},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=time.time() + i * 0.1)
    sg.stop_session(s1["session_id"])

    # Second session at "living_room" with chair moved + same tv
    s2 = sg.start_session("living_room")
    for i in range(20):
        sg.add_detections(s2["session_id"], [
            {"class": "chair", "bbox": [10, 200, 160, 420], "centroid": [85, 310], "confidence": 0.9},
            {"class": "tv", "bbox": [200, 50, 450, 200], "centroid": [325, 125], "confidence": 0.91},
        ], (480, 640), timestamp=time.time() + 100 + i * 0.1)
    sg.stop_session(s2["session_id"])

    td = TemporalDiff(sg)
    result = td.compare_by_location("living_room", s2["session_id"])

    assert result is not None
    assert result["reference_session"]["session_id"] == s1["session_id"]
    assert result["current_session"]["session_id"] == s2["session_id"]

    chair = next(ch for ch in result["changes"] if ch["object"] == "chair")
    assert chair["status"] == "moved"

    shutil.rmtree(tmp)


if __name__ == "__main__":
    test_all_five_statuses()
    print("test_all_five_statuses PASSED")
    test_displacement_formula()
    print("test_displacement_formula PASSED")
    test_shared_neighbor_gate()
    print("test_shared_neighbor_gate PASSED")
    test_location_autodiff()
    print("test_location_autodiff PASSED")
    print("\nALL REGRESSION TESTS PASSED")