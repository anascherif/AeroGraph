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
SAFETY_DIR: Path = DATA_DIR / "safety"


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

# Confidence threshold for keeping a detection.
# Raised from 0.35 → 0.55 to suppress single-frame YOLO hallucinations
# (e.g. small metal objects briefly classified as "person" at conf ~0.45).
# YOLO11n is well-calibrated; 0.55 keeps genuine detections with negligible
# recall loss for clearly-visible objects in demo conditions.
DETECTION_CONFIDENCE: float = float(os.getenv("AEROGRAPH_DET_CONF", "0.55"))

# YOLO input image size (square). Smaller = faster inference, slightly worse
# small-object recall. 416 is the sweet spot for CPU-only real-time; override
# to 640 with the env var if you need maximum small-object sensitivity.
YOLO_IMGSZ: int = int(os.getenv("AEROGRAPH_YOLO_IMGSZ", "416"))

# --- Live-stream detection smoother ---
#
# Per-class rolling-window smoothing applied between YOLO and the spatial
# graph / WebSocket broadcast. Eliminates single-frame flicker and
# hallucinations by requiring a class to appear in ≥ MIN_HITS of the last
# WINDOW frames before it is emitted, and holding it for COOLDOWN_S after
# the last genuine sighting so a 1-2 frame occlusion doesn't make it vanish.
DETECTION_SMOOTHER_WINDOW: int = 5        # remember the last 5 frames
DETECTION_SMOOTHER_MIN_HITS: int = 3     # need 3-of-5 to keep a class
DETECTION_SMOOTHER_COOLDOWN_S: float = 1.5  # hold for 1.5s after last sighting

# Seconds between keyframe captures for the CLIP index
KEYFRAME_INTERVAL_S: float = 3.0

# Pixels per meter approximation for displacement estimation.
# Tunable — assumes a roughly 640px-wide frame from a phone camera a few meters
# away. Adjust during demo calibration.
PIXELS_PER_METER: float = 120.0


# --- Live stream settings ---

# Target frame rate for the detection loop.  On CPU-only with YOLO11n @
# imgsz=416, inference is ~60-90ms, so 8 FPS (125ms interval) leaves
# comfortable headroom for the WebSocket + graph ingestion + smoother work.
# The actual rate adapts: if inference takes longer than the interval, the
# loop simply continues without sleeping.
STREAM_FPS: int = int(os.getenv("AEROGRAPH_STREAM_FPS", "8"))

# JPEG quality (0–100) for the optional frame preview sent over the WebSocket.
# Lower = smaller message, faster transfer. 70 gives a clear-ish image at
# ~30 KB per frame on 640×480.
STREAM_JPEG_QUALITY: int = 70

# Optional SAPI5 voice ID override. Leave empty to auto-detect the first
# English voice on the system (the default). Set to a specific voice ID
# (run `python -c "import pyttsx3; e=pyttsx3.init(); print([v.id for v in e.getProperty('voices')])"`)
# if auto-detection picks the wrong one.
TTS_VOICE_ID: str = os.getenv("AEROGRAPH_TTS_VOICE_ID", "")


# --- Safety monitor (body-cam distress detection) ---
#
# The camera is assumed to be body-worn (chest/head/neck), so the *wearer* is
# never in frame. We detect the camera-side signature of a fall/distress event
# using three orthogonal cheap signals (motion energy, downward tilt from
# optical flow, and brightness drop), fused into a debounced candidate.

SAFETY_MOTION_HISTORY_S: float = 60.0       # rolling window length for motion energy
SAFETY_WAS_MOVING_THRESHOLD: float = 5.0   # min motion magnitude above which we consider the user "was moving"
SAFETY_CONFIRMATION_S: float = 30.0         # voice confirmation window before escalating
SAFETY_CANDIDATE_WINDOW_S: float = 8.0      # how long signals must stick before candidate fires
SAFETY_BRIGHTNESS_DROP_PCT: float = 0.6     # EMA brightness must fall below 40% of baseline
SAFETY_TILT_VERT_FLOW: float = 4.0          # px of vertical optical-flow per frame to call it a downward tilt
SAFETY_COOLDOWN_S: float = 60.0             # cooldown after any alert cycle before re-arming
SAFETY_MIN_SIGNALS: int = 2                 # 2 of 3 must flag simultaneously
SAFETY_STT_LISTEN_PHRASES: tuple[str, ...] = (
    "i'm okay", "i am okay", "im okay", "okay", "ok", "yes", "fine",
    "cancel", "stop", "i'm fine", "i am fine",
)

# --- Notifiers (all env-guarded; absent env = disabled / dry-run) ---

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")  # optional group fallback
WHATSAPP_BRIDGE_URL: str = os.getenv("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:7878")
TWILIO_SID: str = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN: str = os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM: str = os.getenv("TWILIO_FROM", "")

# --- Auth (safety endpoints) ---
# If set, all safety API endpoints require an Authorization: Bearer <token>
# header. If empty, auth is skipped (local dev mode). Set this in .env
# for any non-localhost deployment to prevent contact hijack attacks.
AEROGRAPH_AUTH_TOKEN: str = os.getenv("AEROGRAPH_AUTH_TOKEN", "")


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
    """Create the data / models / sessions / safety directories if missing."""
    for p in (DATA_DIR, MODELS_DIR, CHROMA_PATH, SESSIONS_DIR, SAFETY_DIR):
        p.mkdir(parents=True, exist_ok=True)


# --- Runtime status (populated on startup) ---
class RuntimeState:
    """Mutable holder for cross-module runtime info (loaded models, etc.)."""

    yolo_loaded: bool = False
    chroma_ready: bool = False
    clip_loaded: bool = False
    spatial_graph_ready: bool = False
    camera_streaming: bool = False
    safety_monitor_ready: bool = False
    notifier_bus_ready: bool = False
    telegram_enabled: bool = False
    whatsapp_enabled: bool = False
    twilio_enabled: bool = False
    auth_enabled: bool = False


runtime = RuntimeState()
