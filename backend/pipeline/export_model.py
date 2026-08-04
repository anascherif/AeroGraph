"""One-time helper to download YOLO11n and export it to ONNX for CPU inference.

Usage (run from project root with the venv activated):

    python -m backend.pipeline.export_model

Or call :func:`ensure_onnx_model` programmatically from startup to lazily
create the ONNX file if it is missing.

The export is ``imgsz``-aware: it writes a file whose name encodes the input
size (e.g. ``yolo11n_416.onnx``) so different resolutions can coexist
side-by-side. The detector picks the file matching ``config.YOLO_IMGSZ``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MODELS_DIR, YOLO_IMGSZ

logger = logging.getLogger("aerograph.export")


def _onnx_filename(imgsz: int) -> str:
    """Return the canonical ONNX filename for a given input size."""
    if imgsz == 640:
        return "yolo11n.onnx"  # legacy/default name
    return f"yolo11n_{imgsz}.onnx"


def ensure_onnx_model(pt_name: str = "yolo11n.pt") -> Path:
    """Ensure the ONNX export of ``pt_name`` exists under ``MODELS_DIR``.

    Exports at the imgsz configured in :data:`backend.config.YOLO_IMGSZ`.
    Downloads the ``.pt`` weights on first use (cached by ultralytics).

    Returns the path to the resulting ``.onnx`` file.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODELS_DIR / _onnx_filename(YOLO_IMGSZ)

    if onnx_path.exists():
        logger.info("ONNX model already exists at %s", onnx_path)
        return onnx_path

    from ultralytics import YOLO

    logger.info(
        "Exporting %s -> ONNX (CPU, imgsz=%d) ...", pt_name, YOLO_IMGSZ
    )
    model = YOLO(pt_name)  # auto-downloads weights on first use
    # ultralytics writes the .onnx next to the .pt (cwd or weights dir).
    # It names the file based on imgsz.
    model.export(
        format="onnx",
        imgsz=YOLO_IMGSZ,
        simplify=True,
        opset=17,
        dynamic=False,
        half=False,
        device="cpu",
    )

    # ultralytics always names the output yolo11n.onnx; rename to imgsz-specific.
    legacy = Path.cwd() / "yolo11n.onnx"
    if not onnx_path.exists() and legacy.exists():
        legacy.replace(onnx_path)

    if not onnx_path.exists():
        raise FileNotFoundError(
            f"ONNX export finished but {onnx_path} was not created. "
            f"Checked CWD for yolo11n.onnx."
        )
    logger.info("ONNX model ready at %s", onnx_path)
    return onnx_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = ensure_onnx_model()
    print(f"Model exported to: {path}")
