"""Roster agent — propose the cast + places a newly-created world should start with.

This is the only genuinely new generation step in world population. It answers
"who and where is this world about?" as a short list of ``{name, seed}`` entries;
each seed is then handed to the existing ``character_agent.draft_character`` /
``setting_agent.draft_setting`` so a populated world is drafted by exactly the same
agents the by-hand creators use.

Grounding matches the single-entity draft endpoints: the persisted world
(``world_context``), the author's Draft-selected file text (``docs_block``), and
hybrid retrieval over the world's corpus (``rag_block``).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    LlmConn,
    docs_block,
    extract_json,
    gen_params,
    rag_block,
    resolve_llm_or,
    world_context,
)
from app.schemas.reasoning import ReasoningEffort
from app.schemas.world_populate import (
    MAX_CHARACTERS_CAP,
    MAX_SETTINGS_CAP,
    RosterEntry,
    RosterProposal,
)
from app.services import llm

_SYSTEM = (
    "You are Mytheca's world-population planner. Given a newly-authored "
    "interactive-fiction world, propose the starting cast and the places the story "
    "will return to. Do not write the characters or places themselves — propose a "
    "ROSTER: for each entry a fitting proper name and one seed sentence dense enough "
    "for another writer to flesh it out (who they are and what pressure they are "
    "under; what the place is and why scenes happen there). Make the cast pull "
    "against each other — allies, obstacles, and at least one figure whose interests "
    "cut across the premise — and make every entry unmistakably of THIS world, using "
    "its own proper nouns. Respond with ONLY a JSON object — no prose, no markdown, "
    'no code fences — of the form {"characters": [{"name": "...", "seed": "..."}], '
    '"settings": [{"name": "...", "seed": "..."}]}. Include no other keys.'
)


def _entries(raw: object, cap: int) -> list[RosterEntry]:
    """Coerce the model's list into named entries: drop the nameless, de-dupe, cap.

    Tolerant on purpose — a roster with one unusable row should cost that row, not
    the whole run. De-duplication is case-insensitive so a model that repeats a
    character under two spellings still yields one of them.
    """
    if cap <= 0 or not isinstance(raw, list):
        return []
    out: list[RosterEntry] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        out.append(RosterEntry(name=name, seed=str(item.get("seed") or "").strip()))
        if len(out) >= cap:
            break
    return out


def propose_roster(
    db: Session,
    *,
    storyline_id: str,
    docs_overview: str | None = None,
    max_characters: int = 5,
    max_settings: int = 3,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
    conn: LlmConn | None = None,
) -> RosterProposal:
    """Propose up to ``max_characters`` cast members and ``max_settings`` places.

    Requests nothing when both bounds are zero. Raises the standard ``APIError``
    (400 unconfigured LLM, 502 unparseable reply) — a roster the run cannot get is
    fatal, unlike the per-entity failures downstream.
    """
    max_characters = max(0, min(max_characters, MAX_CHARACTERS_CAP))
    max_settings = max(0, min(max_settings, MAX_SETTINGS_CAP))
    if not max_characters and not max_settings:
        return RosterProposal()

    base_url, api_key, model, params = resolve_llm_or(db, conn)
    ask = (
        f"Propose exactly {max_characters} characters and {max_settings} settings for "
        "this world."
    )
    user = (
        f"{ask}{world_context(db, storyline_id)}"
        f"{docs_block(docs_overview)}{rag_block(db, storyline_id, ask)}"
    )
    data = extract_json(
        llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            gen_params(params),
            reasoning=reasoning,
        )
    )
    return RosterProposal(
        characters=_entries(data.get("characters"), max_characters),
        settings=_entries(data.get("settings"), max_settings),
    )
