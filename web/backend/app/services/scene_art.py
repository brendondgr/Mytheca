"""Setting scene-art generation — ComfyUI → WebP, persisted under MEDIA_DIR.

The setting counterpart to ``services.portraits``: render an
**establishing image** of a place from the agent-written positive/negative
prompts, convert to WebP, and save it under the served media directory. Returns
the relative ``/media/scenes/...`` URL the setting stores in its ``image`` column.

Serves both the Setting Creator and the Scenario Creator, so the art style
(``app.content.art_styles``) reaching this one function is what makes places and scenes
obey the same look as characters.

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
from app.content import art_styles
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
    style: str | None = None,
) -> dict[str, str]:
    """Render an establishing image and persist it. Returns ``{"image": url}``.

    ``style`` is an art-style id; ``None`` uses the operator's stored default.
    """
    positive = (positive or "").strip()
    if not positive:
        raise APIError(400, "bad_request", "A positive prompt is required to generate scene art.")

    comfy = settings_store.get_comfy(db)
    base = settings_store.resolve_comfy_base_url(db, base_url)
    if not base:
        raise APIError(400, "bad_request", "Configure a ComfyUI base URL in Options first.")
    params = comfy.params
    resolved = settings_store.resolve_art_style(db, style)
    positive, styled_negative = art_styles.apply_style(
        positive,
        (negative or "").strip() or params.negative_prompt,
        resolved.style,
        surface="scene",
    )

    image_bytes, _info = comfyui.generate(
        base,
        workflow or comfy.workflow,
        positive=positive,
        negative=styled_negative or None,
        steps=steps or params.steps,
        cfg=cfg if cfg is not None else params.cfg,
        width=width or _SCENE_W,
        height=height or _SCENE_H,
        seed=seed if seed is not None else random.randint(0, _SEED_MAX),
        batch_size=1,
        lora_name=resolved.lora_name or None,
        lora_strength=resolved.lora_strength,
        lora_enabled=resolved.lora_enabled,
    )

    filename = save_webp(_scenes_dir(), image_bytes)
    return {"image": f"/media/scenes/{filename}"}
