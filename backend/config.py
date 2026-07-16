"""Central configuration for AeroGraph backend.

Loads environment variables from .env (if present) and exposes typed settings
to the rest of the application.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve project root: backend/config.py -> backend/ -> project root
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Load .env from project root if it exists
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


# --- NVIDIA NIM (LLM) ---
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "glm-5.1")

# --- Groq (Speech-to-Text) ---
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

# --- Camera ---
# "0" for default webcam, or an HTTP URL for an IP-camera app
CAMERA_SOURCE: str = os.getenv("CAMERA_SOURCE", "0")


def _resolve_camera_source(source: str) -> int | str:
    """Return an int for webcam indices or the original string for URLs."""
    if source.isdigit():
        return int(source)
    return source


CAMERA_SOURCE_PARSED: int | str = _resolve_camera_source(CAMERA_SOURCE)


# --- Paths ---
DATA_DIR: Path = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
MODELS_DIR: Path = PROJECT_ROOT / os.getenv("MODELS_DIR", "backend/models")
CHROMA_PATH: Path = PROJECT_ROOT / os.getenv("CHROMA_PATH", "data/chroma")


# --- Detection pipeline constants ---

# YOLO11n COCO classes relevant for spatial navigation & memory.
# Full COCO list: https://docs.ultralytics.com/datasets/detect/coco/
# We keep a focused subset per the brief ("not everything — just what matters
# for navigation and memory").
DETECTION_CLASSES: list[str] = [
    # People
    "person",
    # Vehicles (outdoor navigation / hazards)
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    # Furniture / structural anchors
    "bench",
    "chair",
    "couch",
    "bed",
    "dining table",
    "toilet",
    "potted plant",
    # Electronics / appliances
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "sink",
    "refrigerator",
    # Personal items / portable hazards
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    # Kitchenware / small objects
    "bottle",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    # Food (common on tables)
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    # Misc decor / small items
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
]

# Confidence threshold for keeping a detection
DETECTION_CONFIDENCE: float = 0.35

# Seconds between keyframe captures for the CLIP index
KEYFRAME_INTERVAL_S: float = 3.0

# Pixels per meter approximation for displacement estimation.
# Tunable — assumes a roughly 640px-wide frame from a phone camera a few meters
# away. Adjust during demo calibration.
PIXELS_PER_METER: float = 120.0


# --- Spatial graph / session settings ---

# Where per-session manifests are persisted (one JSON file per session).
SESSIONS_DIR: Path = DATA_DIR / "sessions"

# Time window (seconds) used to group detections into "scenes".
# Detections closer together than this in time are assumed to come from
# roughly the same camera viewpoint.
SCENE_WINDOW_S: float = 3.0

# Maximum gap (seconds) between two detections of the same class before we
# consider them separate sightings (object left the scene and came back).
SIGHTING_GAP_S: float = 6.0

# Minimum number of frames an object must appear in to be considered a
# "stable" entry in the scene (filters out flickering / single-frame noise).
MIN_FRAMES_FOR_STABLE: int = 2

# Pixel distance (in normalised centroid coords, 0-1) that a centroid must
# shift between two sessions for the object to be flagged as "moved".
CENTROID_SHIFT_THRESHOLD: float = 0.12


# --- Object categories for temporal diff ---
# Used by the diff engine to classify the *importance* of a change.
# "hazard" classes are the most important for navigation warnings.

OBJECT_CATEGORIES: dict[str, str] = {
    **{c: "anchor" for c in [
        "bench", "chair", "couch", "bed", "dining table", "toilet",
        "potted plant", "tv", "sink", "refrigerator", "oven", "microwave",
    ]},
    **{c: "hazard" for c in [
        "bottle", "backpack", "handbag", "suitcase", "umbrella", "box",
        "scissors", "knife", "bowl", "vase", "teddy bear",
    ]},
    **{c: "personal" for c in [
        "cell phone", "laptop", "mouse", "remote", "keyboard", "book",
        "cup", "fork", "spoon", "clock", "tie", "person",
    ]},
}


def object_category(class_name: str) -> str:
    """Return the category for a class, defaulting to ``"personal"``."""
    return OBJECT_CATEGORIES.get(class_name, "personal")


def ensure_dirs() -> None:
    """Create the data / models / sessions directories if missing."""
    for p in (DATA_DIR, MODELS_DIR, CHROMA_PATH, SESSIONS_DIR):
        p.mkdir(parents=True, exist_ok=True)


# --- Runtime status (populated on startup) ---
class RuntimeState:
    """Mutable holder for cross-module runtime info (loaded models, etc.)."""

    yolo_loaded: bool = False
    chroma_ready: bool = False
    clip_loaded: bool = False
    spatial_graph_ready: bool = False


runtime = RuntimeState()
