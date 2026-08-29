"""Style blocks — the six fields a storyline's narrative style guide is made of.

A style guide says **how this story is written**, never what happens in it. The World
Primer is the world as fact; this is the world as prose. Six named blocks, each optional,
each independently editable and clearable at the storyline and the scenario level.

| id | governs | who reads it | where it lands |
| --- | --- | --- | --- |
| ``attention`` | what gets felt, dwelt on, or passed over | prose agents | cached system prefix |
| ``voice`` | how people in this world sound | prose agents | cached system prefix |
| ``pacing`` | what a turn is *for*, narrate-vs-speak bias | the planner | planner system message |
| ``texture`` | the world's recurring specifics | prose agents | cached system prefix |
| ``never`` | this world's failure modes | prose **and** planner | both system messages |
| ``signature`` | the whole guide compressed to one clause | prose agents | the volatile recency tail |

**Placement is the load-bearing decision, not the block list.** Five of the six ride in a
system message that is byte-identical for every speaker and every beat of a scene, so an
inference server's prefix cache keeps them warm and they are paid for **once per scene**.
Only ``signature`` sits in the recency tail, where every beat re-reads it — which is why it
is one clause and not a paragraph.

**The placement is justified by cost, not by measured quality, and that distinction is
load-bearing.** ``EXP-2026-08-018`` reported that a guide in the cached prefix changes the
prose; ``EXP-2026-08-019`` re-ran that experiment's *unchanged* baseline on the same prompts
and it moved by more than the reported effect. So no number here supports "the guide improves
the writing" — what the prefix placement buys is that four of the six blocks cost nothing
after the first beat of a scene, which is worth having whether or not the guide is doing
anything. ``signature`` is the one block that is NOT free per beat and is therefore the one
that needs a result it does not have; it is recorded as a deletion candidate in
``docs/checklist.md``.

**Block ids are a persisted contract.** They are stored on ``storylines.style_blocks`` and
``scenarios.style_blocks`` and sent on request bodies. Never rename one without migrating
stored values; :func:`get` falls back to ``None`` rather than raising, because an unknown id
from a stale client must be ignored, not 422'd.

**No block may contain a count.** Not paragraphs, not beats, not sentences, not words. The
three-tier ``beatLength`` control and the ``maxTurns`` cap were removed for exactly this
reason, and ``EXP-2026-08-007`` measured a word count moving the average the *wrong* way. A
test in ``utils/tests/backend/data/test_style_presets.py`` scans the built-ins for one.

**Block text is literal and never interpolated.** No ``{Character}``, no register, no live
stat values. One templated token makes the block volatile and destroys the cache placement
above, which is the whole reason the blocks are worth having in the prefix at all.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Who consumes a block. ``prose`` is the character/narrator/scene-script agents (they share
#: one stable prefix); ``planner`` is the beat planner; ``both`` is exactly what it says.
Reader = str  # "prose" | "planner" | "both"

#: Where a block lands in the prompt. ``prefix`` is the cached system region; ``tail`` is the
#: volatile recency window that is re-read on every single beat.
Placement = str  # "prefix" | "tail"


@dataclass(frozen=True)
class StyleBlock:
    """One field of a style guide: what it governs, who reads it, where it lands."""

    id: str
    label: str
    #: One line under the field in the editor. Says what the block is *for*, in the author's
    #: language — never "this string is appended to the system prompt".
    helper: str
    #: The example placeholder shown in an empty field. Deliberately a fragment rather than a
    #: full block, so it reads as a hint and not as text to keep.
    placeholder: str
    reader: Reader
    placement: Placement


ATTENTION = StyleBlock(
    id="attention",
    label="Attention",
    helper="What the prose dwells on, and what it passes over quickly.",
    placeholder="Dwell on what people do with their hands while they answer something else…",
    reader="prose",
    placement="prefix",
)

VOICE = StyleBlock(
    id="voice",
    label="Voice",
    helper="How people in this world sound — the shape of their sentences, not their accents.",
    placeholder="People here talk around the thing. Answers arrive one clause short…",
    reader="prose",
    placement="prefix",
)

PACING = StyleBlock(
    id="pacing",
    label="Pacing",
    helper="What a turn is for: when to narrate, when to let someone speak, what to withhold.",
    placeholder="End a turn slightly before it is satisfying. Prefer narration that changes…",
    reader="planner",
    placement="prefix",
)

TEXTURE = StyleBlock(
    id="texture",
    label="Texture",
    helper="The recurring specifics that make the world feel lived-in.",
    placeholder="Weather is always present and always slightly wrong for the hour…",
    reader="prose",
    placement="prefix",
)

NEVER = StyleBlock(
    id="never",
    label="Never",
    helper="This world's failure modes — the moves that break the spell.",
    placeholder="Never let a character recap what has already happened…",
    reader="both",
    placement="prefix",
)

SIGNATURE = StyleBlock(
    id="signature",
    label="Signature",
    helper="The whole guide in one clause. This is the only part re-read on every beat, so keep it short.",
    placeholder="Low and slow. Withhold more than you give.",
    reader="prose",
    placement="tail",
)

#: Editor display order — every surface renders the fields in exactly this order.
STYLE_BLOCKS: tuple[StyleBlock, ...] = (ATTENTION, VOICE, PACING, TEXTURE, NEVER, SIGNATURE)

#: Emission order for the PROSE system prefix. Fixed, and fixed here rather than at the
#: render site: the rendered bytes have to be identical every time or the prefix cache misses,
#: and a dict's iteration order is not a contract anyone should be relying on for that.
PREFIX_ORDER: tuple[str, ...] = (ATTENTION.id, VOICE.id, TEXTURE.id, NEVER.id)

#: Emission order for the PLANNER system message. ``never`` appears in both, deliberately —
#: a world's failure modes are as much about which beats get planned as how they get written.
PLANNER_ORDER: tuple[str, ...] = (PACING.id, NEVER.id)

_BY_ID = {block.id: block for block in STYLE_BLOCKS}


def ids() -> list[str]:
    """Every known block id, in editor display order."""
    return [block.id for block in STYLE_BLOCKS]


def get(block_id: str | None) -> StyleBlock | None:
    """One block by id, or ``None`` for an unknown/stale id.

    Falls back rather than raising: a saved guide carrying a key this build does not know
    must be ignored the way ``prompt_registry`` ignores an unknown prompt key, not rejected.
    """
    return _BY_ID.get((block_id or "").strip())
