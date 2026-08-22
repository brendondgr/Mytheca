"""Art styles — the three looks every generated image in Mytheca can wear.

One authored catalog, read by both halves of the image pipeline:

* the **prompt-writing agents** (``character_agent`` · ``setting_agent`` ·
  ``scenario_agent`` · ``moment_agent``) interpolate a style's :attr:`~ArtStyle.model_hint`
  and its per-surface tag string into their system prompts, so the model is *told* what
  look to write toward;
* the **render services** (``portraits`` · ``scene_art`` · ``scene_moment``) run the
  finished prompts through :func:`apply_style` so the tags are present even when nobody
  asked an agent — the player's hand-written repaint prompt in ``SceneImageModal`` is
  exactly that case — and hand the style's LoRA decision to ``services.comfyui``.

Three styles, in display order:

| id | look | LoRA out of the box |
| --- | --- | --- |
| ``painted`` | watercolor/oil washes — the house look, and the default | ``zit_watercolor.safetensors`` @ 0.8 |
| ``anime`` | cel-shaded anime illustration | none (the workflow's LoRA node is bypassed) |
| ``photoreal`` | photograph | none |

``painted``'s tag strings are the ones the four agents carried as literals before styles
existed, moved here **verbatim**, so a default render is unchanged by this catalog.

The two non-painted styles ship LoRA-less on purpose: no anime LoRA is installed, and the
base checkpoint (``zit_intorealism_zitV60``) is already realism-leaning. Every style's LoRA
file, strength and on/off flag is an operator setting (``settings_store.resolve_art_style``),
so pointing ``anime`` at a LoRA is a change in Options, not a change in this file.

**Style ids are a persisted contract** — they are stored in the ``comfy`` settings row and
sent on request bodies. Never rename one without migrating stored values. :func:`get`
falls back to the default rather than raising, because an image request must not fail
because a stale client named a style that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass

#: How the in-play moment shot is always framed, whatever the style is. Lives here (rather
#: than in ``moment_agent``, which re-exports it) because every style's ``moment_tags``
#: has to carry it — a portrait-orientation moment image is a bug in any look.
LANDSCAPE_TAG = "wide landscape composition"

#: Which surface a prompt is for. Each names a different shot, so each gets its own tags.
Surface = str  # "portrait" | "scene" | "moment"


@dataclass(frozen=True)
class ArtStyle:
    """One selectable look: what the agent is told, what gets appended, which LoRA."""

    id: str
    label: str
    #: One line for the picker, naming the look rather than the settings behind it.
    blurb: str
    #: How the agent's system prompt describes the model it is writing for.
    model_hint: str
    portrait_tags: str
    scene_tags: str
    moment_tags: str
    #: The style-dependent slice of a negative prompt — what THIS look must not drift into.
    #: The style-independent half (text, watermark, deformed hands…) stays with each agent.
    negative_tags: str
    #: ``None`` means the workflow's LoRA node is bypassed for this style.
    default_lora: str | None = None
    default_lora_strength: float = 0.8

    def tags_for(self, surface: Surface) -> str:
        """The tag string for one surface (unknown surface → the scene tags)."""
        if surface == "portrait":
            return self.portrait_tags
        if surface == "moment":
            return self.moment_tags
        return self.scene_tags


PAINTED = ArtStyle(
    id="painted",
    label="Painted",
    blurb="Watercolor and oil washes — Mytheca's house look.",
    model_hint="a painterly watercolor and oil image model",
    portrait_tags=(
        "watercolor portrait, soft washes, painterly, delicate linework, warm lighting, "
        "head and shoulders, detailed face"
    ),
    scene_tags=(
        "watercolor, soft washes, painterly, atmospheric, establishing shot, wide view, "
        "no people, detailed environment"
    ),
    moment_tags=(
        "watercolor, soft washes, painterly, delicate linework, atmospheric lighting, "
        f"{LANDSCAPE_TAG}, detailed"
    ),
    negative_tags="photorealistic, 3d render",
    default_lora="zit_watercolor.safetensors",
    default_lora_strength=0.8,
)

ANIME = ArtStyle(
    id="anime",
    label="Anime",
    blurb="Cel-shaded illustration with clean, bold linework.",
    model_hint="an anime illustration model",
    portrait_tags=(
        "anime portrait, cel shaded, clean bold linework, expressive eyes, vibrant flat "
        "colors, anime key visual, head and shoulders, detailed face"
    ),
    scene_tags=(
        "anime background art, cel shaded, clean linework, vibrant colors, atmospheric, "
        "establishing shot, wide view, no people, detailed environment"
    ),
    moment_tags=(
        "anime illustration, cel shaded, clean bold linework, expressive faces, vibrant "
        f"colors, dramatic lighting, {LANDSCAPE_TAG}, detailed"
    ),
    negative_tags="photorealistic, 3d render, western cartoon",
)

PHOTOREAL = ArtStyle(
    id="photoreal",
    label="Photoreal",
    blurb="A photograph — natural texture and cinematic light.",
    model_hint="a photorealistic image model",
    portrait_tags=(
        "photorealistic portrait, photograph, natural skin texture, shallow depth of "
        "field, cinematic lighting, 85mm lens, head and shoulders, high detail"
    ),
    scene_tags=(
        "photorealistic, photograph, natural light, atmospheric haze, establishing shot, "
        "wide view, no people, high detail"
    ),
    moment_tags=(
        "photorealistic, photograph, natural skin texture, cinematic lighting, film grain, "
        f"{LANDSCAPE_TAG}, high detail"
    ),
    negative_tags="illustration, painting, drawing, anime, cartoon, 3d render",
)

#: Display order — the picker renders them in exactly this order everywhere.
ART_STYLES: tuple[ArtStyle, ...] = (PAINTED, ANIME, PHOTOREAL)

#: What an unset, unknown, or stale style id resolves to. ``painted`` because it is the
#: look every image in the product wore before styles existed.
DEFAULT_STYLE_ID = PAINTED.id

_BY_ID = {style.id: style for style in ART_STYLES}


def ids() -> list[str]:
    """Every known style id, in display order."""
    return [style.id for style in ART_STYLES]


def catalog() -> tuple[ArtStyle, ...]:
    """The full catalog, in display order."""
    return ART_STYLES


def get(style_id: str | None) -> ArtStyle:
    """The named style, or the default for ``None`` / blank / unknown."""
    return _BY_ID.get((style_id or "").strip(), PAINTED)


# ---- applying a style to a finished prompt ---------------------------------


def _phrases(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split(",") if p.strip()]


def _append_missing(text: str, tags: str) -> str:
    """Append whichever comma phrases of ``tags`` ``text`` does not already carry.

    Case-insensitive, so an agent that wrote ``Watercolor`` is not given a second copy.
    Idempotent by construction: running it twice adds nothing the second time.
    """
    have = {p.lower() for p in _phrases(text)}
    missing = [p for p in _phrases(tags) if p.lower() not in have]
    if not missing:
        return (text or "").strip()
    base = (text or "").strip().rstrip(",")
    return ", ".join([base, *missing]) if base else ", ".join(missing)


def _foreign(style: ArtStyle, pick) -> set[str]:
    """The phrases another style claims and this one does not — lower-cased.

    Phrases shared across styles (``wide view``, ``detailed face``, ``3d render`` in the
    negatives) are by construction absent from this set, so they are never stripped.
    """
    mine = {p.lower() for p in _phrases(pick(style))}
    return {
        p.lower()
        for other in ART_STYLES
        if other.id != style.id
        for p in _phrases(pick(other))
    } - mine


def _restyle(text: str, tags: str, foreign: set[str]) -> str:
    kept = [p for p in _phrases(text) if p.lower() not in foreign]
    return _append_missing(", ".join(kept), tags)


def apply_style(
    positive: str, negative: str | None, style: ArtStyle, *, surface: Surface
) -> tuple[str, str]:
    """Return ``(positive, negative)`` wearing ``style``'s look for ``surface``.

    Two moves, in order: **drop** any phrase that belongs to one of the *other* styles
    (and not to this one), then **append** whichever of this style's tags are missing.

    The drop is what makes a style switch actually switch. A prompt stored when the
    character was painted still ends in ``watercolor portrait, soft washes``; re-rendering
    it as ``photoreal`` while leaving those in produces a muddle. Worse in the negatives:
    ``painted`` and ``anime`` both push ``photorealistic`` away, which would flatly
    contradict a ``photoreal`` render. Phrases every style shares survive untouched.

    Idempotent, and additive with respect to everything the writer chose that is not a
    competing style tag. Called at the render boundary, so agent-written prompts, the
    player's hand-written repaint prompt, and prompts stored under an older style all
    render in the style that was actually asked for.
    """
    return (
        _restyle(positive, style.tags_for(surface), _foreign(style, lambda s: s.tags_for(surface))),
        _restyle(negative or "", style.negative_tags, _foreign(style, lambda s: s.negative_tags)),
    )
