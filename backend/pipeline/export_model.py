"""One-time helper to download YOLO11n and export it to ONNX for CPU inference.

Usage (run from project root with the venv activated):

    python -m backend.pipeline.export_model

Or call :func:`ensure_onnx_model` programmatically from startup to lazily
create the ONNX file if it is missing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MODELS_DIR

logger = logging.getLogger("aerograph.export")


def ensure_onnx_model(pt_name: str = "yolo11n.pt") -> Path:
    """Ensure the ONNX export of ``pt_name`` exists under ``MODELS_DIR``.

    Downloads the ``.pt`` weights (auto-cached by ultralytics) and exports to
    ONNX with ``imgsz=640, simplify=True, device="cpu"``. Returns the path to
    the resulting ``.onnx`` file.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODELS_DIR / pt_name.replace(".pt", ".onnx")

    if onnx_path.exists():
        logger.info("ONNX model already exists at %s", onnx_path)
        return onnx_path

    from ultralytics import YOLO

    logger.info("Exporting %s -> ONNX (CPU, imgsz=640, simplify=True) ...", pt_name)
    model = YOLO(pt_name)  # auto-downloads weights on first use
    model.export(
        format="onnx",
        imgsz=640,
        simplify=True,
        opset=17,
        dynamic=False,
        half=False,
        device="cpu",
    )

    # ultralytics writes the .onnx next to the .pt (cwd or weights dir).
    # Locate it and move into MODELS_DIR if not already there.
    candidate = Path(pt_name).with_suffix(".onnx")
    if not onnx_path.exists() and candidate.exists():
        candidate.replace(onnx_path)

    if not onnx_path.exists():
        raise FileNotFoundError(
            f"ONNX export finished but {onnx_path} was not created. "
            f"Checked candidate {candidate.resolve()}."
        )
    logger.info("ONNX model ready at %s", onnx_path)
    return onnx_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = ensure_onnx_model()
    print(f"Model exported to: {path}")
