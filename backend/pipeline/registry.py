"""Shared runtime singletons for AeroGraph pipeline components.

These are initialised lazily (on FastAPI startup or on first use) and held
for the lifetime of the process so that API routers and pipeline stages can
access the loaded models without re-initialising them on every request.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.pipeline.detector import Detector

logger = logging.getLogger("aerograph.registry")


# Held instances (populated on startup)
detector: Optional[Detector] = None


def get_detector() -> Detector:
    """Return the shared :class:`Detector`, raising if it is not loaded."""
    if detector is None:
        raise RuntimeError("Detector has not been initialised yet.")
    return detector
