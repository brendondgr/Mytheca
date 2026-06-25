"""Setting scene-art generation — ComfyUI → WebP, persisted under MEDIA_DIR.

The setting counterpart to ``services.portraits``: render a watercolor
**establishing image** of a place from the agent-written positive/negative
prompts, convert to WebP, and save it under the served media directory. Returns
the relative ``/media/scenes/...`` URL the setting stores in its ``image`` column.

Like portraits it uses a **fresh random seed** each call (so re-rendering yields a
new image and ComfyUI actually executes rather than serving a cached result), and
reuses the same ComfyUI client/workflow + the shared WebP helpers. Scene art
defaults to a **landscape 1024×576 (16:9)** frame — places read as vistas, not
head-and-shoulders — overridable by the caller.
"""

from __future__ import annotations

import random
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.services import comfyui, settings_store
from app.services.media import save_webp

# Default establishing-shot frame — 16:9 landscape (both divisible by 8).
_SCENE_W = 1024
_SCENE_H = 576
_SEED_MAX = 2**32 - 1


def _scenes_dir() -> Path:
    """Directory scene-art images are written to (patched in tests)."""
    return get_settings().scenes_dir


def generate_scene_art(
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
    seed: int | None = None,
) -> dict[str, str]:
    """Render a watercolor establishing image and persist it. Returns ``{"image": url}``."""
    positive = (positive or "").strip()
    if not positive:
        raise APIError(400, "bad_request", "A positive prompt is required to generate scene art.")

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
        width=width or _SCENE_W,
        height=height or _SCENE_H,
        seed=seed if seed is not None else random.randint(0, _SEED_MAX),
        batch_size=1,
    )

    filename = save_webp(_scenes_dir(), image_bytes)
    return {"image": f"/media/scenes/{filename}"}
