"""Shared media helpers — ComfyUI PNG → WebP conversion + persistence.

One source of truth for the "convert the rendered image to WebP and write it under
the served media directory" step, used by both the character portrait pipeline
(``services.portraits``) and the setting scene-art pipeline (``services.scene_art``).
Keeping it here stops the two from drifting (and from duplicating the conversion).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.errors import APIError

_WEBP_QUALITY = 90


def to_webp(image_bytes: bytes) -> bytes:
    """Convert raw image bytes (PNG from ComfyUI) to WebP."""
    try:
        with Image.open(BytesIO(image_bytes)) as im:
            rgb = im.convert("RGB")
            out = BytesIO()
            rgb.save(out, format="WEBP", quality=_WEBP_QUALITY, method=6)
            return out.getvalue()
    except (OSError, ValueError) as exc:
        raise APIError(
            502, "upstream_error", "The generated image could not be converted to WebP."
        ) from exc


def save_webp(directory: Path, image_bytes: bytes) -> str:
    """Convert to WebP, write under ``directory`` with a random name, return the filename."""
    webp = to_webp(image_bytes)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.webp"
    (directory / filename).write_bytes(webp)
    return filename
