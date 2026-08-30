"""What the turn does not know, and goes to read before it writes.

The structured engine gates retrieval with a regex (``services/retrieval_gate``): it fires on
a capitalised word that is not on the roster, or on a wh-question paired with a history cue,
and skips on doubt. That is the right trade there — a per-beat prose call cannot afford a
round trip to decide whether to make another round trip, and a missed fetch only costs
grounding.

Free-text can afford it, and the owner's example is exactly what a regex cannot have: the
scene is about to involve an ogre, and what an *ogre* is **in this world** may be nothing like
the usual meaning. A keyword rule sees a common noun and skips. A model reading the scene sees
something it cannot write about honestly and says so.

So this agent is asked one question — *what would you look up?* — and answers with search
terms, never prose. The engine runs them through the same hybrid retrieval the rest of the app
uses and folds the results into the volatile tail as reference material.

**Best-effort in every direction.** No endpoint, an unparseable reply, an empty vector store,
a term that matches nothing: all of them mean the turn writes without extra grounding, which
is exactly what every turn did before this existed. It may never fail a turn.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import RAG_SNIPPET_CHARS, decision_timeout, extract_json, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import freetext_context, llm
from app.services.assembler import TurnContext

logger = logging.getLogger("mytheca.turn")

#: Deciding what to read is a quick, structural judgement — the owner's figure is 128–256
#: thinking tokens. ``LOW`` is the upper end of that, and this call runs once per turn.
LOOKUP_EFFORT = ReasoningEffort.LOW

#: How many terms one turn may chase. Three is already generous for a single exchange, and
#: each one is a vector query plus prompt budget spent on material the scene may never touch.
MAX_TERMS = 3

#: How much of one retrieved entry reaches the prompt. Matches the structured engine's snippet
#: cap so the two paths ground on comparable amounts of text rather than one quietly reading
#: more of the corpus than the other.
SNIPPET_CHARS = RAG_SNIPPET_CHARS

#: Ceiling on the whole reference block, so a broad term cannot crowd out the scene itself.
BLOCK_CHARS = 3000

_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_TERMS}
    },
    "required": ["terms"],
}


def terms_for(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    pov=None,
) -> list[str]:
    """Ask what this turn needs to read. ``[]`` on any failure, and on the common answer.

    Composed through :func:`freetext_context.messages`, so this call shares its prefix with
    every other call in the turn — the lookup is the *first* call, so it is the one that pays
    for the prefix and warms it for the rest.
    """
    instruction = ctx.prompts.get(prompt_registry.FREETEXT_LOOKUP, _INSTRUCTION)
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return []
    messages = freetext_context.messages(
        ctx, turn_beats, instruction=instruction, lore="", pov=pov
    )
    try:
        raw = llm.chat_complete(
            base_url, api_key, model, messages, params,
            reasoning=LOOKUP_EFFORT,
            extra_body={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "lookup_terms", "schema": _SCHEMA},
                }
            },
            timeout_s=decision_timeout(),
        )
        data = extract_json(raw)
    except APIError:
        # One retry unconstrained, for the same reason the planner has one: an endpoint with
        # no `response_format` support rejects the request outright, and treating that as
        # "this scene gets no lookups" would punish a whole class of server for a feature
        # this call does not need.
        try:
            raw = llm.chat_complete(
                base_url, api_key, model, messages, params,
                reasoning=LOOKUP_EFFORT, timeout_s=decision_timeout(),
            )
            data = extract_json(raw)
        except APIError:
            logger.debug("lookup: endpoint unavailable; writing ungrounded")
            return []

    raw_terms = data.get("terms")
    if not isinstance(raw_terms, list):
        return []
    seen: list[str] = []
    known = {m.name.strip().lower() for m in ctx.cast}
    if ctx.setting is not None:
        known.add(str(ctx.setting.name or "").strip().lower())
    for entry in raw_terms:
        term = str(entry or "").strip()
        # A term naming somebody already fully described in the cached prefix is a wasted
        # query and, worse, retrieves the character sheet the prompt already holds — so the
        # model reads its own context back as though it were new information.
        if not term or term.lower() in known or term.lower() in {t.lower() for t in seen}:
            continue
        seen.append(term)
        if len(seen) >= MAX_TERMS:
            break
    return seen


def lore_block(db: Session, storyline_id: str | None, terms: list[str]) -> str:
    """Retrieve each term and fold the hits into one bounded reference block.

    Deliberately **not** ``_common.rag_block``: that helper takes one query and frames the
    result for an authoring draft. Here there are several terms and the framing has to say
    something stronger — this is background the scene may lean on, never a thing to recite.
    """
    if not storyline_id or not terms:
        return ""
    try:
        from app.rag.retriever import retrieve
    except Exception:  # pragma: no cover - defensive; retrieval never blocks a turn
        return ""

    seen_ids: set[str] = set()
    lines: list[str] = []
    for term in terms:
        try:
            entries = retrieve(db, storyline_id, term)
        except Exception:  # pragma: no cover - a down store is a no-op, never an error
            logger.debug("lookup: retrieval failed for %r", term, exc_info=True)
            continue
        for entry in entries:
            if entry.entry_id in seen_ids:
                continue
            seen_ids.add(entry.entry_id)
            body = entry.body[:SNIPPET_CHARS].strip()
            if body:
                lines.append(f"- {entry.name} ({entry.type}): {body}")
    if not lines:
        return ""
    block = "\n".join(lines)[:BLOCK_CHARS]
    return (
        "WHAT THE WORLD'S OWN RECORDS SAY about what you asked to look up. Stay consistent "
        "with this; never quote it, read it aloud, or have anyone mention the records "
        "themselves:\n" + block
    )


_INSTRUCTION = prompt_registry.default(prompt_registry.FREETEXT_LOOKUP)
