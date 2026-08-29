"""Style guide — resolve a storyline's narrative style and render it into prompt text.

The one owner of "what style is in force, composed how?", the way
``settings_store.resolve_art_style`` is the one answer to "what look, with which LoRA?".
Everything that decides *bytes* lives here, because the prefix-cache design rests on two
renders of the same guide producing the same string, and two modules deciding that is how
one of them ends up wrong.

**Two layers, not three.** ``storyline → scenario``. This is a deliberate divergence from
``prompt_registry.resolve_prompts`` (``global → storyline → scenario``): a *global* style
guide would push one voice onto every world, which is the opposite of the point. Saved
presets are a **library, not a layer** — applying one copies its text into a storyline's own
fields. Do not "fix" this into a three-layer chain.

**The scenario override is an appended delta, never an in-place rewrite.** Rewriting a block
inside the storyline's guide would diverge the cached prefix at that block and discard
everything after it; appending moves the divergence to the last bytes of the system message,
and hands the override the recency advantage on top. The cost — the model sees both versions
— is paid by the delta's explicit precedence line. Whether that is enough is *measurable*,
and is recorded as unmeasured rather than assumed.

The ``signature`` block is the exception: it rides in the volatile recency tail, which is
re-read every beat anyway, so it resolves **in place** (last non-blank layer wins) and no
delta is involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from app.content import style_blocks

#: Header of the prose style block in the cached system prefix.
_PREFIX_HEADER = "HOW THIS STORY IS WRITTEN"
#: Header of the pacing block in the planner's system message.
_PLANNER_HEADER = "HOW THIS STORY IS PACED"
#: Header of the scenario delta, and the sentence that resolves the conflict it creates.
_DELTA_HEADER = (
    "FOR THIS SCENE ONLY — the blocks below replace the ones above. Where they conflict, "
    "these win."
)

_TRAILING_SPACE = re.compile(r"[ \t]+$", re.M)
_BLANK_RUN = re.compile(r"\n{3,}")


def normalize(text: str | None) -> str:
    """One block's text, reduced to canonical bytes.

    Byte-stability is a requirement here, not a nicety: the block sits in a system message
    whose whole value is being byte-identical across every beat of a scene. Two authors
    pasting visually identical text must produce identical bytes, and the same stored value
    must render the same way every time.

    Normalises line endings, strips trailing whitespace per line, collapses runs of blank
    lines, and strips the ends. Blank in, empty string out — which every caller reads as
    "this block is absent", never as "this block is empty".
    """
    if not text:
        return ""
    cleaned = str(text).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _TRAILING_SPACE.sub("", cleaned)
    cleaned = _BLANK_RUN.sub("\n\n", cleaned)
    return cleaned.strip()


def normalize_blocks(blocks: Mapping[str, object] | None) -> dict[str, str]:
    """A stored block map, cleaned: known ids only, normalised, blanks dropped.

    Unknown ids are dropped rather than rejected — a guide saved by a newer build, or a key
    a stale client invented, must be ignored the way ``prompt_registry`` ignores an unknown
    prompt key. Ordering is not preserved and deliberately so: every render orders blocks
    from ``style_blocks``, never from the stored dict.
    """
    if not blocks:
        return {}
    out: dict[str, str] = {}
    for key, value in blocks.items():
        block = style_blocks.get(str(key))
        if block is None or not isinstance(value, str):
            continue
        text = normalize(value)
        if text:
            out[block.id] = text
    return out


@dataclass(frozen=True)
class ResolvedStyle:
    """The style in force for one scene, as two layers plus the rendering rules."""

    storyline: dict[str, str] = field(default_factory=dict)
    scenario: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when no block is set at either layer — the pre-feature state."""
        return not self.storyline and not self.scenario

    def block(self, block_id: str) -> str:
        """One block's live value, scenario winning — for the tail, not the prefix."""
        return self.scenario.get(block_id) or self.storyline.get(block_id) or ""

    # ---- Rendering ------------------------------------------------------------------

    def render_prefix(self) -> str:
        """The prose style text for the CACHED system prefix.

        Emitted as the storyline's guide in full, then — only if the scene overrides
        something — an appended delta. See the module docstring for why the delta is
        appended rather than substituted in place.
        """
        body = _render_section(_PREFIX_HEADER, self.storyline, style_blocks.PREFIX_ORDER)
        delta = _render_section(_DELTA_HEADER, self.scenario, style_blocks.PREFIX_ORDER)
        if body and delta:
            return f"{body}\n\n{delta}"
        # A scene may override a block the world never set. The delta then stands alone,
        # and still carries its precedence line — it reads as an instruction either way.
        return body or delta

    def render_planner(self) -> str:
        """The pacing text for the PLANNER's system message.

        The planner is the only reader of ``pacing``: how a turn is shaped is a decision
        about which beats exist, which is its job and not the prose agents'. ``never`` rides
        along because a world's failure modes are as much about what gets planned.
        """
        body = _render_section(_PLANNER_HEADER, self.storyline, style_blocks.PLANNER_ORDER)
        delta = _render_section(_DELTA_HEADER, self.scenario, style_blocks.PLANNER_ORDER)
        if body and delta:
            return f"{body}\n\n{delta}"
        return body or delta

    def render_signature(self) -> str:
        """The one-clause handle for the volatile recency TAIL, or ``""``.

        Resolved in place (scenario wins) rather than as a delta: the tail is re-read on
        every beat regardless, so there is no cached prefix to protect here, and showing the
        model two competing one-liners would be a cost with nothing bought by it.
        """
        signature = self.block(style_blocks.SIGNATURE.id)
        if not signature:
            return ""
        return f"The style of this story, in one line: {signature}"


def _render_section(header: str, blocks: dict[str, str], order: tuple[str, ...]) -> str:
    """One headed section, or ``""`` when it would be empty.

    An absent block emits **nothing at all** — no label, no blank line, no scaffolding. An
    empty heading would be both a lie to the model and a source of byte drift.
    """
    parts: list[str] = []
    for block_id in order:
        text = blocks.get(block_id)
        if not text:
            continue
        block = style_blocks.get(block_id)
        label = block.label if block else block_id.title()
        parts.append(f"{label}. {text}")
    if not parts:
        return ""
    return "\n\n".join([header, *parts])


def resolve(
    storyline_blocks: Mapping[str, object] | None,
    scenario_blocks: Mapping[str, object] | None = None,
) -> ResolvedStyle:
    """The style in force for a scene: the world's guide, plus this scene's overrides.

    A block present at the scenario layer with a blank value means **inherit**, not
    "override with nothing" — the same rule ``prompt_registry.resolve_prompts`` follows, and
    the same subtlety: getting it backwards would make a cleared field look like a
    customisation. ``normalize_blocks`` drops blanks, so this falls out for free.
    """
    storyline = normalize_blocks(storyline_blocks)
    scenario = normalize_blocks(scenario_blocks)
    # A scene that "overrides" a block with text identical to the world's is not an override.
    # Dropping it keeps the cached prefix whole for a scene that changed nothing, which is
    # the common case when a guide is copied around by hand.
    scenario = {k: v for k, v in scenario.items() if storyline.get(k) != v}
    return ResolvedStyle(storyline=storyline, scenario=scenario)


def resolve_for(storyline, scenario=None) -> ResolvedStyle:
    """:func:`resolve`, reading the ORM rows directly. The call site the assembler uses."""
    return resolve(
        getattr(storyline, "style_blocks", None) if storyline is not None else None,
        getattr(scenario, "style_blocks", None) if scenario is not None else None,
    )
