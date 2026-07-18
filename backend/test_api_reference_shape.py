"""Regression test: ``SpatialGraph.get_objects()`` response shape must match
``backend/API_REFERENCE.md``.

This test exists because the API reference doc drifted from the backend on
two occasions:

1. The doc previously listed ``object_id``, ``class_name``, ``centroid_px``,
   ``bbox_px``, ``neighbours`` — none of which actually appear in the response.
   Corrected in a prior commit to use the real keys: ``class``, ``last_bbox``,
   ``last_center``, ``co_occurred_with``, ``total_frames``, ``avg_confidence``.
2. The doc later (incorrectly) added a ``category`` field to the session
   objects response, but ``get_objects()`` never sets ``category`` — that
   field is computed only at query-time by ``object_category()`` (used in
   ``query_engine.py`` and ``temporal_diff._diff_same_class``).

This test asserts the EXACT set of keys returned per object so any future
addition/removal in the response shape triggers a failure here, prompting
the developer to update the API reference in the same commit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.pipeline.spatial_graph import SpatialGraph


# These are the keys that ``API_REFERENCE.md`` promises to front-end callers
# for the ``GET /v1/session/{id}/objects`` endpoint. If you change this set,
# you MUST update the example block in backend/API_REFERENCE.md too.
EXPECTED_OBJECT_KEYS: set[str] = {
    "class",
    "total_frames",
    "first_seen",
    "last_seen",
    "last_bbox",
    "last_centroid",
    "frame_w",
    "frame_h",
    "avg_confidence",
    "co_occurred_with",
}


def test_get_objects_shape_matches_docs() -> None:
    """``get_objects()`` must return exactly the documented keys — no more,
    no less.  Notably, NO ``category`` key (that is computed at query-time
    by ``object_category()``, not by the spatial graph).
    """
    with tempfile.TemporaryDirectory() as tmp:
        sg = SpatialGraph(sessions_dir=Path(tmp))
        manifest = sg.start_session("kitchen")
        sid = manifest["session_id"]

        # Feed enough frames to cross MIN_FRAMES_FOR_STABLE so the object
        # actually appears in get_objects() output. We reuse the same
        # scene by staying inside the SCENE_WINDOW_S gap between calls.
        detections_seen = []
        for i in range(5):
            ts = 1_700_000_000.0 + i * 0.5  # 0.5s apart → same scene
            sg.add_detections(
                sid,
                [
                    {
                        "class": "cup",
                        "bbox": [300 + i, 220, 340 + i, 260],
                        "centroid": [320 + i, 240],
                        "confidence": 0.90 + i * 0.01,
                    },
                    {
                        "class": "bottle",
                        "bbox": [400, 180, 450, 250],
                        "centroid": [425, 215],
                        "confidence": 0.85,
                    },
                ],
                (480, 640),
                timestamp=ts,
            )
            detections_seen.append(ts)

        objects = sg.get_objects(sid)
        assert objects, (
            "Expected at least one object in get_objects() — "
            "either MIN_FRAMES_FOR_STABLE was not met or scene ageing changed."
        )

        for obj in objects:
            keys = set(obj.keys())
            assert keys == EXPECTED_OBJECT_KEYS, (
                f"get_objects() returned a key set that does NOT match the "
                f"API_REFERENCE.md example.\n"
                f"  Expected: {sorted(EXPECTED_OBJECT_KEYS)}\n"
                f"  Got:      {sorted(keys)}\n"
                f"  Extra:    {sorted(keys - EXPECTED_OBJECT_KEYS)}\n"
                f"  Missing:  {sorted(EXPECTED_OBJECT_KEYS - keys)}\n"
                f"If you intentionally changed the response shape, update "
                f"both this test AND backend/API_REFERENCE.md in the same "
                f"commit to prevent future drift."
            )

            # Specifically assert 'category' is NOT present — it has been
            # wrongly listed in the docs before. The diff change dicts DO
            # carry 'category' (set by _moved_change/_new_change etc.), but
            # the spatial graph's per-object response does not.
            assert "category" not in keys, (
                "'category' must NOT appear in get_objects() response — "
                "it is computed at query-time by object_category()."
            )
            assert "class_name" not in keys, (
                "'class_name' must NOT appear — use 'class' (matches detector output)."
            )
            assert "object_id" not in keys, (
                "'object_id' must NOT appear — objects are keyed by class name."
            )

            # Value-type sanity checks (also asserted by the docs)
            assert isinstance(obj["class"], str)
            assert obj["class"] in ("cup", "bottle")
            assert isinstance(obj["total_frames"], int) and obj["total_frames"] >= 5
            assert isinstance(obj["last_bbox"], list) and len(obj["last_bbox"]) == 4
            assert isinstance(obj["last_centroid"], list) and len(obj["last_centroid"]) == 2
            assert isinstance(obj["co_occurred_with"], list)  # set is sorted to list
            assert all(isinstance(n, str) for n in obj["co_occurred_with"])

    print("test_get_objects_shape_matches_docs PASSED")


if __name__ == "__main__":
    test_get_objects_shape_matches_docs()
    print()
    print("API_REFERENCE DRIFT REGRESSION TEST PASSED")
