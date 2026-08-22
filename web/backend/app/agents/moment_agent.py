"""Moment-prompt agent — the live scene → a ComfyUI prompt for what is happening.

The player's **Create image** action is two-stage: this module is stage one. It
reads the scene as it stands (world, place, the last few beats, and who is in
frame) and writes the positive/negative prompts for an image of *the moment* —
then ``services.scene_moment`` renders them.

The whole difficulty is that an image model cannot look up a name. "Maerin closes
her ledger" paints a random woman; "weathered harbor-mistress in a salt-stained
oilskin coat, closing a brass-cornered ledger" paints *her*. So the system prompt
demands appearance-and-action phrasing for every figure in the shot, and
:func:`strip_names` enforces it deterministically afterwards by rewriting any name
the model leaked into that character's own **visual tag** — the opening phrases of
the portrait prompt that produced their avatar, i.e. their established look.

Composition is fixed (landscape, in-frame subjects) and the style tags follow the
art style the portrait and scene-art agents already establish, so a captured
moment sits beside a character portrait as the same kind of object. The *subject*
is deliberately open — whatever the scene happens to be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    LlmConn,
    extract_json,
    gen_params,
    resolve_llm_or,
)
from app.content import art_styles
from app.content.art_styles import ArtStyle
from app.core.errors import APIError
from app.schemas.play import MomentPromptResponse
from app.schemas.reasoning import ReasoningEffort
from app.services import llm

# How the shot is always framed, whatever the scene is. Appended when the model
# omits it so the rendered frame is never portrait-orientation by accident. Defined in
# ``art_styles`` (every style's moment tags must carry it) and re-exported here, which is
# where callers and tests have always looked for it.
LANDSCAPE_TAG = art_styles.LANDSCAPE_TAG

# The style-independent half of a negative prompt — what no illustration of a scene should
# show, in any look. The style's own negatives are prepended by ``_default_negative``.
BASE_NEGATIVE = (
    "text, watermark, signature, caption, speech bubble, "
    "extra limbs, deformed hands, extra fingers, blurry, lowres, cropped"
)


def _default_negative(style: ArtStyle) -> str:
    """Used when the model returns no negative prompt of its own."""
    return f"{BASE_NEGATIVE}, {style.negative_tags}"

def _moment_system(style: ArtStyle) -> str:
    """The in-play moment system prompt, written for one art style."""
    return (
    f"You are Mytheca's moment-prompt writer for {style.model_hint} "
    "(Z-Image-Turbo via ComfyUI). You are given a live roleplay scene: the world, "
    "the place, who is in frame, and the last beats of the transcript. Write the "
    "prompts for a single illustration of WHAT IS HAPPENING RIGHT NOW in that "
    "scene. The model responds best to SHORT phrases separated by commas — not "
    "sentences. Respond with ONLY a JSON object — no prose, no fences — with "
    'exactly three string keys: "positive", "negative", "caption".\n'
    "positive: 14-24 short comma-separated phrases, in this order.\n"
    "  1. The shot: the moment as an action (e.g. 'two figures facing each other "
    "across a lamplit table', 'a lone rider cresting a burning ridge').\n"
    "  2. EVERY figure in frame, one after another, each described ONLY by "
    "appearance and by what they are DOING in this moment — species/race, age, "
    "build, hair, distinguishing marks, clothing, then their posture, gesture, and "
    "expression right now. Use the appearance details given for each character; do "
    "not invent a different look for them, and do not merge two characters into "
    "one.\n"
    "  3. The place: its kind, its materials, the light, the weather, the mood.\n"
    f"  4. Style tags: '{style.moment_tags}'.\n"
    "NEVER write a character's NAME, nickname, or title-plus-name in the positive "
    "prompt — the image model cannot look a name up, and a name wastes the phrase "
    "that should have described the person. Write what a viewer would SEE.\n"
    "negative: a comma-separated list of what to avoid — always include 'text, "
    "watermark, signature, extra limbs, deformed hands, blurry, lowres', plus "
    "anything this particular scene should not show.\n"
    "caption: ONE short sentence of plain English describing the picture, for a "
    "reader who cannot see it. Names ARE allowed here."
    )


@dataclass(frozen=True)
class FramedCharacter:
    """One character in the shot, as the prompt writer sees them.

    ``portrait_positive`` is the ComfyUI prompt that produced their avatar — already
    phrase-shaped, and the most reliable statement of what they look like, which is
    why it doubles as the fallback :func:`visual_tag` when a name must be rewritten.
    """

    id: str
    name: str
    role: str = ""
    appearance: str = ""
    portrait_positive: str = ""
    doing: str = ""


def visual_tag(character: FramedCharacter) -> str:
    """A few words that identify a character by look, used to replace their name.

    Prefers the first phrases of their portrait prompt (already comma-separated
    appearance phrases), then the first clause of their appearance prose, then their
    role. Falls back to a neutral figure so a replacement is always possible.
    """
    source = (character.portrait_positive or "").strip()
    if source:
        phrases = [p.strip() for p in source.split(",") if p.strip()]
        if phrases:
            return ", ".join(phrases[:2])
    prose = (character.appearance or "").strip()
    if prose:
        first = re.split(r"[.;]", prose)[0].strip()
        if first:
            return first[:80]
    role = (character.role or "").strip()
    return role.lower() if role else "a figure"


# Name tokens that are also ordinary words — replacing these would mangle the
# prompt ("hopeful expression" → "<tag>ful expression"). Full names still match.
_COMMON_WORDS = {
    "hope",
    "grace",
    "faith",
    "rose",
    "dawn",
    "storm",
    "river",
    "ash",
    "hunter",
    "smith",
    "wolf",
    "king",
    "queen",
    "lord",
    "lady",
    "brother",
    "sister",
    "father",
    "mother",
    "captain",
    "doctor",
    "the",
}


def _name_forms(name: str) -> list[str]:
    """Every form of a name worth matching, longest first.

    The full name, then each token of it that is long enough and not an ordinary
    word — so "Maerin Voss" also catches a bare "Maerin", but "Brother Hope" does
    not turn every "hope" in the prompt into a person.
    """
    name = (name or "").strip()
    if not name:
        return []
    forms = {name}
    for token in re.split(r"[\s,'’\-]+", name):
        token = token.strip(".")
        if len(token) >= 4 and token.lower() not in _COMMON_WORDS:
            forms.add(token)
    return sorted(forms, key=len, reverse=True)


def strip_names(text: str, characters: list[FramedCharacter]) -> str:
    """Rewrite any character name in ``text`` as that character's visual tag.

    The guard behind the feature's central requirement: the prompt must describe
    people, not name them. Matching is case-insensitive and word-bounded, longest
    form first, and each character's own name is removed from their tag first so a
    replacement can never reintroduce it.
    """
    if not text:
        return text
    for character in characters:
        tag = visual_tag(character)
        forms = _name_forms(character.name)
        if not forms:
            continue
        # A tag that contains the name would smuggle it straight back in.
        for form in forms:
            tag = re.sub(rf"\b{re.escape(form)}\b", "", tag, flags=re.IGNORECASE)
        tag = re.sub(r"\s{2,}", " ", tag).strip(" ,") or "a figure"
        pattern = "|".join(re.escape(form) for form in forms)
        text = re.sub(rf"\b(?:{pattern})(?:'s|’s)?\b", tag, text, flags=re.IGNORECASE)
    # Replacement can leave doubled separators behind ("a figure, , lamplit").
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(,\s*){2,}", ", ", text)
    return text.strip(" ,")


def _cast_block(cast: list[FramedCharacter]) -> str:
    """Render the in-frame characters for the prompt — look first, name last."""
    lines: list[str] = []
    for i, c in enumerate(cast, start=1):
        bits = [f"Figure {i} (never name them; they are {c.name}):"]
        if c.role:
            bits.append(f"  Role: {c.role}")
        if c.appearance:
            bits.append(f"  Appearance: {c.appearance}")
        if c.portrait_positive:
            bits.append(f"  Established look (phrases): {c.portrait_positive}")
        if c.doing:
            bits.append(f"  Doing right now: {c.doing}")
        lines.append("\n".join(bits))
    return "\n".join(lines)


def write_moment_prompt(
    db: Session,
    *,
    beats: list[str],
    cast: list[FramedCharacter] | None = None,
    world: str = "",
    place: str = "",
    style: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
    conn: LlmConn | None = None,
) -> MomentPromptResponse:
    """Write the ComfyUI prompts for an image of the scene's current moment.

    ``beats`` are the recent transcript lines (oldest → newest) and are required —
    there is no moment to paint before the scene has said anything. ``cast`` is who
    is in frame; an empty cast is legitimate (an empty room, a landscape). ``style`` is an
    art-style id (``app.content.art_styles``); unknown/omitted falls back to the default.
    """
    art_style = art_styles.get(style)
    cast = cast or []
    beats = [b.strip() for b in beats if (b or "").strip()]
    if not beats:
        raise APIError(
            400, "bad_request", "Play at least one beat before capturing the moment."
        )

    base_url, api_key, model, params = resolve_llm_or(db, conn)
    sections = []
    if world.strip():
        sections.append(world.strip())
    if place.strip():
        sections.append(f"Place:\n{place.strip()}")
    if cast:
        sections.append(f"In frame:\n{_cast_block(cast)}")
    sections.append("Recent beats (oldest first; the LAST one is the moment):\n" + "\n".join(beats))

    messages = [
        {"role": "system", "content": _moment_system(art_style)},
        {"role": "user", "content": "\n\n".join(sections)},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )

    positive = strip_names(str(data.get("positive") or "").strip(), cast)
    if not positive:
        raise APIError(502, "upstream_error", "The image prompt came back empty.")
    if "landscape" not in positive.lower():
        positive = f"{positive}, {LANDSCAPE_TAG}"
    negative = str(data.get("negative") or "").strip() or _default_negative(art_style)
    # The caption is read by people, not by the image model — names help there.
    caption = str(data.get("caption") or "").strip()

    return MomentPromptResponse(positive=positive, negative=negative, caption=caption)
