"""Relationship extractor — seed character↔character graph edges from authored bios.

The story graph defines feeling/standing/knowledge edge types (``content/graph_registry``)
but nothing ever wrote them, so a character never knew how they felt about anyone. This
agent reads the cast's authored bios (role, background, personality, secret, goal) and
proposes the **initial** directed relationships among them — "Mei distrusts Beth", "Beth
resents Mei" — using only the registry's character↔character edge types. The cold path
then evolves these during play (Reactive Turn Director D4 / P5).

Structure-only, roster- and type-constrained, **best-effort** → ``[]``. Takes a
pre-resolved LLM connection (not a ``Session``) so it can run off the request thread.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents._common import extract_json, gen_params
from app.agents.reflection_agent import LlmConn
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort

RELATIONSHIP_EFFORT = ReasoningEffort.LOW

# The character↔character edge types the extractor may use (from the graph registry):
# feelings (§5.1), standing (§5.5), and knowledge (§5.4). Setting/faction/event edges
# are out of scope here.
RELATIONSHIP_TYPES: dict[str, str] = {
    "loves": "A loves B.",
    "trusts": "A trusts B.",
    "fears": "A fears B.",
    "resents": "A resents B.",
    "allied_with": "A is allied with B.",
    "at_war_with": "A is openly hostile to B.",
    "knows": "A knows B (personally / a fact about them).",
    "suspects": "A suspects B (of something).",
}

_SYSTEM = """You seed the initial relationships between the characters of a story from their authored bios. Return directed relationships that are stated or clearly implied by the bios — STRUCTURE ONLY, never prose.

Return ONLY a JSON object:
{"edges": [{"source": <roster number>, "type": "<relationship type>", "target": <roster number>, "reason": "<short why, from the bios>"}]}

Allowed relationship types (use ONLY these): loves, trusts, fears, resents, allied_with, at_war_with, knows, suspects.

Rules:
- Directed: "source" feels/stands toward "target". Add the reverse only if the bios support it too.
- Use ONLY the roster numbers given; source and target must differ.
- Include an edge only when the bios actually support it — omit rather than invent. Few strong edges beat many weak guesses.
- No prose, no commentary — just the JSON object."""


@dataclass
class RelationshipEdge:
    """One directed character→character relationship to write to the graph."""

    source_id: str
    type: str
    target_id: str
    reason: str = ""


def extract(conn: LlmConn, characters: list[dict]) -> list[RelationshipEdge]:
    """Propose initial relationship edges among ``characters`` (best-effort → ``[]``).

    ``characters`` is an ordered list of ``{"id", "name", "bio"}``.
    """
    if len(characters) < 2:
        return []
    from app.services import llm

    base_url, api_key, model, params = conn
    roster_ids = {i + 1: c["id"] for i, c in enumerate(characters)}
    roster = "\n\n".join(
        f"[{i + 1}] {c['name']}\n{(c.get('bio') or '').strip() or '(no bio)'}"
        for i, c in enumerate(characters)
    )
    user = f"Characters:\n{roster}\n\nList the relationships among them."
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            gen_params(params),
            reasoning=RELATIONSHIP_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return []

    edges: list[RelationshipEdge] = []
    seen: set[tuple[str, str, str]] = set()
    raw_edges = data.get("edges", [])
    for item in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(item, dict):
            continue
        etype = str(item.get("type", "")).strip().lower()
        if etype not in RELATIONSHIP_TYPES:
            continue
        source = roster_ids.get(_as_int(item.get("source")) or -1)
        target = roster_ids.get(_as_int(item.get("target")) or -1)
        if source is None or target is None or source == target:
            continue
        key = (source, etype, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append(RelationshipEdge(source, etype, target, str(item.get("reason", "")).strip()))
    return edges


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return None
