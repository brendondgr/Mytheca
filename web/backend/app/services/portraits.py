"""Character portrait generation — ComfyUI → WebP, persisted under MEDIA_DIR.

Wraps the proven ``services.comfyui.generate`` pipeline for the Character
Creator: resolve the configured Comfy server + workflow + default params, render
a watercolor portrait from the agent-written positive/negative prompts, convert
the PNG output to **WebP** (the chosen avatar format), and save it under the
served media directory. Returns the relative ``/media/...`` URL the character
stores in its ``portrait`` column.

The ComfyUI client and the bundled workflow stay untouched — conversion happens
at the edge here. Portrait orientation defaults to a tall frame (better for a
face) but the caller may override the size.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.services import comfyui, settings_store

# Default portrait frame (divisible by 8 for the latent grid); overridable.
_PORTRAIT_W = 768
_PORTRAIT_H = 1024
_WEBP_QUALITY = 90


def _portraits_dir() -> Path:
    """Directory portraits are written to (patched in tests)."""
    return get_settings().portraits_dir


def _to_webp(image_bytes: bytes) -> bytes:
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


def generate_portrait(
    db: Session,
    positive: str,
    negative: str | None = None,
    *,
    base_url: str | None = None,
    workflow: str | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
) -> dict[str, str]:
    """Render a watercolor portrait and persist it as WebP. Returns ``{"portrait": url}``."""
    positive = (positive or "").strip()
    if not positive:
        raise APIError(400, "bad_request", "A positive prompt is required to generate a portrait.")

    comfy = settings_store.get_comfy(db)
    base = settings_store.resolve_comfy_base_url(db, base_url)
    if not base:
        raise APIError(400, "bad_request", "Configure a ComfyUI base URL in Options first.")
    params = comfy.params

    image_bytes, _info = comfyui.generate(
        base,
        workflow or comfy.workflow,
        positive=positive,
        negative=(negative or "").strip() or params.negative_prompt or None,
        steps=steps or params.steps,
        cfg=cfg if cfg is not None else params.cfg,
        width=width or _PORTRAIT_W,
        height=height or _PORTRAIT_H,
        batch_size=1,
    )

    webp = _to_webp(image_bytes)
    directory = _portraits_dir()
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.webp"
    (directory / filename).write_bytes(webp)
    return {"portrait": f"/media/portraits/{filename}"}
