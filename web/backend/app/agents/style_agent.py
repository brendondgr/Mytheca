"""Style agent — draft a world's NARRATIVE STYLE GUIDE, or recognise one that already fits.

The direct sibling of ``storyline_agent.generate_world_primer``: both turn the seed +
premise into agent-facing runtime context, and both run once at creation and are editable
forever after. The primer says what is TRUE in the world; this says how it is WRITTEN.

**Two outcomes, one call.** The agent is handed the current preset catalog — the built-ins
plus whatever the author has saved — and answers with either the id of one that genuinely
fits, or a freshly written guide when none does. Recognising a fit is what makes the preset
library compound: an author's saved guide gets reused rather than quietly re-invented
slightly worse each time. A returned preset id is resolved to its **text**, copied into the
world's own fields; nothing stores a reference, so editing that preset later cannot rewrite
a world that already shipped with it.

**The one thing the output is checked for is a COUNT.** "Two to three paragraphs", "keep it
under 40 words" — a writing agent reaches for that unprompted, and it is exactly what
``EXP-2026-08-007`` measured moving prose the wrong way, and why the ``beatLength`` tiers and
``maxTurns`` were removed. A block carrying one is dropped rather than stored.

Best-effort throughout: an unreachable endpoint, an unparseable reply, or a hallucinated
preset id all resolve to "no style", which is a perfectly ordinary state for an optional
feature — never a 500 in the middle of creating a world.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    docs_block,
    extract_json,
    gen_params,
    resolve_llm,
)
from app.content import style_blocks
from app.schemas.reasoning import ReasoningEffort
from app.services import llm, settings_store, style_guide

logger = logging.getLogger("mytheca.authoring")

#: A length instruction expressed as a quantity. Deliberately broad — it is cheaper to drop
#: an innocent block than to let a count reach the prompt, and the author can rewrite it.
#: Mirrors the check in ``utils/tests/backend/data/test_style_presets.py``.
_COUNT = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[\s-]+"
    r"(to[\s-]+\w+[\s-]+)?"
    r"(word|words|sentence|sentences|paragraph|paragraphs|line|lines|beat|beats|turn|turns)\b",
    re.I,
)

_SYSTEM = """You are Mytheca's style editor. You are given a world, and a shelf of existing style guides. Decide how stories in this world should be WRITTEN — not what happens in them.

A style guide is six short blocks of prose:
- "attention": what the prose dwells on, and what it passes over quickly.
- "voice": how people in this world sound — the shape of their sentences.
- "pacing": what a turn is for; when to narrate, when to let someone speak, what to withhold.
- "texture": the recurring specifics that make the world feel lived-in.
- "never": this world's failure modes — the moves that break the spell.
- "signature": the whole guide compressed into ONE short clause.

First look at the shelf. If one of those guides genuinely fits this world, reply with ONLY:
{"preset": "<its id>"}

Otherwise write one. Reply with ONLY a JSON object whose keys are the six block names above and whose values are strings. Do not include any other key, no prose, no markdown, no code fences.

Rules for what you write:
- Say HOW, never WHAT. "Report violence flatly" is style; "the duke dies in act two" is plot, and does not belong here.
- NEVER give a count of any kind — no number of words, sentences, paragraphs, beats or turns. Length is decided by the moment, and a count is the one instruction that reliably makes the writing worse.
- Write instructions to a writer, in the imperative. Concrete beats abstract: "describe the discovering — the reaching, the light falling wrong" beats "be atmospheric".
- Every block is optional. Leave one out entirely rather than filling it with something generic; a blank block says nothing, which is better than saying nothing at length.
- Keep "signature" to a single clause. It is the only part re-read on every beat.
- Never write a placeholder like {character} or {name}. The text is used exactly as written."""


def _catalog_block(db: Session) -> str:
    """The shelf the agent chooses from, as ``id — name: blurb`` lines."""
    lines = []
    for preset in settings_store.list_style_presets(db):
        blurb = preset.get("blurb") or ""
        lines.append(f"{preset['id']} — {preset['name']}: {blurb}".rstrip(": "))
    if not lines:
        return ""
    return "\n\nExisting style guides on the shelf:\n" + "\n".join(lines)


def clean_blocks(raw: object) -> dict[str, str]:
    """A model reply's blocks, reduced to what is safe to store.

    Unknown keys and non-strings are dropped by ``style_guide.normalize_blocks``; a block
    carrying a length count is dropped *here*, loudly enough to find in a log. Dropping one
    block rather than rejecting the whole guide is the right trade: five good blocks and a
    missing one is a usable guide, and the author can write the sixth.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned = style_guide.normalize_blocks(raw)
    out: dict[str, str] = {}
    for block_id, text in cleaned.items():
        match = _COUNT.search(text)
        if match:
            logger.warning(
                "style agent: dropped %s — it contains a length count (%r)",
                block_id,
                match.group(0),
            )
            continue
        out[block_id] = text
    return out


def draft_style_guide(
    db: Session,
    premise: str | None,
    seed: str | None = None,
    docs_overview: str | None = None,
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> dict[str, str]:
    """The world's style guide: a preset that fits, or a fresh one. ``{}`` on any failure.

    Returns block TEXT either way — a chosen preset is resolved here so the caller never has
    to know which of the two paths ran, and so the guide the author edits is their own copy.
    """
    premise = (premise or "").strip()
    seed = (seed or "").strip()
    if not premise and not seed:
        # No world to read yet. Not an error: the caller offers this beside the primer, and
        # the primer refuses the same way.
        return {}

    parts: list[str] = []
    if seed:
        parts.append(f"One-sentence seed: {seed}")
    if premise:
        parts.append(f"Premise:\n{premise}")
    user = "\n\n".join(parts) + docs_block(docs_overview) + _catalog_block(db)

    try:
        base_url, api_key, model, params = resolve_llm(db)
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            gen_params(params),
            reasoning=reasoning,
        )
        data = extract_json(raw)
    except Exception as exc:  # noqa: BLE001 - an optional feature never breaks world creation
        logger.warning("style agent: draft failed (%s); continuing with no style", exc)
        return {}

    if not isinstance(data, dict):
        return {}

    chosen = data.get("preset")
    if isinstance(chosen, str) and chosen.strip():
        blocks = settings_store.get_style_preset_blocks(db, chosen)
        if blocks:
            # Copied, never referenced — see the module docstring.
            return blocks
        # A hallucinated id. Fall through to whatever else the reply carried rather than
        # failing: the model may have sent both, and an empty guide is the worse answer.
        logger.info("style agent: unknown preset %r; using the written blocks instead", chosen)

    return clean_blocks({k: v for k, v in data.items() if k in set(style_blocks.ids())})
