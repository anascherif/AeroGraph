"""Shared runtime singletons for AeroGraph pipeline components.

These are initialised lazily (on FastAPI startup or on first use) and held
for the lifetime of the process so that API routers and pipeline stages can
access the loaded models without re-initialising them on every request.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.pipeline.detector import Detector
from backend.pipeline.spatial_graph import SpatialGraph

logger = logging.getLogger("aerograph.registry")


# Held instances (populated on startup)
detector: Optional[Detector] = None
spatial_graph: Optional[SpatialGraph] = None


def get_detector() -> Detector:
    """Return the shared :class:`Detector`, raising if it is not loaded."""
    if detector is None:
        raise RuntimeError("Detector has not been initialised yet.")
    return detector


def get_spatial_graph() -> SpatialGraph:
    """Return the shared :class:`SpatialGraph`, raising if it is not loaded."""
    if spatial_graph is None:
        raise RuntimeError("SpatialGraph has not been initialised yet.")
    return spatial_graph
