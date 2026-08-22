"""Character portrait generation — ComfyUI → WebP, persisted under MEDIA_DIR.

Wraps the proven ``services.comfyui.generate`` pipeline for the Character
Creator: resolve the configured Comfy server + workflow + default params, render
a portrait from the agent-written positive/negative prompts, convert
the PNG output to **WebP** (the chosen avatar format), and save it under the
served media directory. Returns the relative ``/media/...`` URL the character
stores in its ``portrait`` column.

The look is an **art style** (``app.content.art_styles``) — the caller's choice, else the
operator's global default. It decides two things here: the tags
:func:`art_styles.apply_style` guarantees are on the prompts, and whether the workflow's
LoRA node is patched or bypassed.

The ComfyUI client and the bundled workflow stay untouched — conversion happens
at the edge here. Portraits render as a **portrait 832×1216 (2:3)** frame by
default — taller than wide, to suit character cards and the profile hero — but the
caller may override the size. (Scene art keeps its landscape 1024×576 frame.)

Every render uses a **fresh random seed** so re-rendering a character produces a
genuinely new image. It also avoids a ComfyUI stall: with a fixed seed an
identical prompt is served from cache (no GPU execution), and because the
completion WebSocket only connects *after* the prompt is queued, that near-instant
cached signal is missed and the wait loop blocks until its deadline.
"""

from __future__ import annotations

import random
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.content import art_styles
from app.services import comfyui, settings_store
from app.services.media import save_webp, to_webp

# Default portrait frame — portrait 832×1216 (2:3, both divisible by 8 for the
# latent grid); overridable by the caller.
_PORTRAIT_W = 832
_PORTRAIT_H = 1216
# ComfyUI seed bound — kept within unsigned 32-bit for broad node compatibility.
_SEED_MAX = 2**32 - 1

# WebP conversion is shared with the scene-art pipeline; kept aliased here so the
# portrait-service tests (and any callers) keep their familiar reference.
_to_webp = to_webp


def _portraits_dir() -> Path:
    """Directory portraits are written to (patched in tests)."""
    return get_settings().portraits_dir


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
    seed: int | None = None,
    style: str | None = None,
) -> dict[str, str]:
    """Render a portrait and persist it as WebP. Returns ``{"portrait": url}``.

    ``style`` is an art-style id; ``None`` uses the operator's stored default.

    ``seed`` defaults to a fresh random value each call so re-rendering yields a
    new image (and the render actually executes rather than serving a cached one).
    """
    positive = (positive or "").strip()
    if not positive:
        raise APIError(400, "bad_request", "A positive prompt is required to generate a portrait.")

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
        surface="portrait",
    )

    image_bytes, _info = comfyui.generate(
        base,
        workflow or comfy.workflow,
        positive=positive,
        negative=styled_negative or None,
        steps=steps or params.steps,
        cfg=cfg if cfg is not None else params.cfg,
        width=width or _PORTRAIT_W,
        height=height or _PORTRAIT_H,
        seed=seed if seed is not None else random.randint(0, _SEED_MAX),
        batch_size=1,
        lora_name=resolved.lora_name or None,
        lora_strength=resolved.lora_strength,
        lora_enabled=resolved.lora_enabled,
    )

    filename = save_webp(_portraits_dir(), image_bytes)
    return {"portrait": f"/media/portraits/{filename}"}
