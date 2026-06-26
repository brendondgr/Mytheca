"""World-build orchestrator — the New Storyline page's *Build the whole world*.

One creation-time operation that drafts an entire world for review, over the
configured LLM (same plumbing as the other authoring agents):

* ``build_world`` — from a seed and/or dropped reference docs, draft the storyline
  metadata, the World Primer, the universal **stat schema**, a **cast** of full
  characters, and a set of **settings**, and assemble them into a ``ProposedWorld``.

Nothing is persisted here — the page reviews the proposal and commits it through
the normal CRUD endpoints, rendering images (if ComfyUI is configured) at commit
time. To stay affordable the build makes one LLM call per entity: storyline draft
+ primer + one **blueprint** call (stat schema + cast/setting concepts) + one draft
per character + one draft per setting. Image *prompts* are NOT generated here; the
commit step reuses the existing per-entity prompt/render endpoints.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents import character_agent, setting_agent, storyline_agent
from app.agents._common import DOCS_CAP, docs_block, extract_json, gen_params, resolve_llm
from app.core.errors import APIError
from app.schemas.build import (
    MAX_CHARACTERS,
    MAX_SETTINGS,
    MAX_STATS,
    BuildCharacterEvent,
    BuildDoneEvent,
    BuildEvent,
    BuildMetaEvent,
    BuildPlanEvent,
    BuildPrimerEvent,
    BuildSettingEvent,
    BuildStatusEvent,
    ProposedCharacter,
    ProposedSetting,
    ProposedStartingStat,
    ProposedStat,
    ProposedStoryline,
    ProposedWorld,
)
from app.schemas.stat import StatBand
from app.services import llm

_DEFAULT_CHARACTERS = 4
_DEFAULT_SETTINGS = 3
_DEFAULT_STATS = 4

# A non-empty stand-in seed when the author builds from dropped files alone — the
# underlying draft agents require a seed string, but the docs carry the substance.
_DOCS_ONLY_SEED = "Build a coherent world grounded in the provided reference documents."

_BLUEPRINT_SYSTEM = (
    "You are Velora's world-architect producing a build BLUEPRINT for an "
    "interactive-fiction world. Given the world brief, design three things: (1) the "
    "world's universal STAT schema — the bounded numeric values every character "
    "shares (health, morale, suspicion, etc.); (2) a CAST of distinct character "
    "concepts; and (3) a set of SETTING concepts (places the story returns to). "
    "Respond with ONLY a JSON object — no prose, no markdown, no code fences — of "
    'the form {"stats": [{"displayName": "Health", "description": "Physical '
    'condition.", "min": 0, "max": 100, "default": 100, "bands": [{"min": 0, "max": '
    '20, "label": "Nearly dead"}, {"min": 81, "max": 100, "label": "Very healthy"}]}], '
    '"characters": ["one vivid sentence describing a character", ...], "settings": '
    '["one vivid sentence describing a place", ...]}.\n'
    "Each stat needs 2-4 labeled bands that name what value ranges MEAN. Each "
    "concept is a single sentence a downstream agent will flesh out. Keep everything "
    "consistent with the world brief."
)


def _slug(name: str) -> str:
    """Port of the frontend ``statKeyOf`` — a stable lowercase stat key."""
    return re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", name.strip().lower()))


def _int(value: object, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return fallback
    return fallback


def _clamp_count(value: int | None, default: int, cap: int) -> int:
    return max(0, min(cap, default if value is None else value))


def _sanitize_bands(rows: object, lo: int, hi: int) -> list[StatBand]:
    bands: list[StatBand] = []
    if not isinstance(rows, list):
        return bands
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        bmin = max(lo, min(hi, _int(row.get("min"), lo)))
        bmax = max(lo, min(hi, _int(row.get("max"), hi)))
        if bmin > bmax:
            bmin, bmax = bmax, bmin
        bands.append(StatBand(min=bmin, max=bmax, label=label))
    return bands


def _sanitize_stat(row: object, taken: set[str]) -> ProposedStat | None:
    """Coerce a model stat row into a persistable ProposedStat (range-valid)."""
    if not isinstance(row, dict):
        return None
    name = str(row.get("displayName") or row.get("display_name") or "").strip()
    if not name:
        return None
    key = _slug(name) or "stat"
    base, n = key, 2
    while key in taken:
        key = f"{base}_{n}"
        n += 1
    taken.add(key)

    lo = _int(row.get("min"), 0)
    hi = _int(row.get("max"), 100)
    if lo >= hi:
        lo, hi = 0, 100
    default = max(lo, min(hi, _int(row.get("default"), lo)))
    return ProposedStat(
        key=key,
        display_name=name,
        description=str(row.get("description") or "").strip(),
        min=lo,
        max=hi,
        default=default,
        bands=_sanitize_bands(row.get("bands"), lo, hi),
    )


def _world_brief(meta: ProposedStoryline) -> str:
    parts = [f"World: {meta.title} ({meta.genre})."]
    if meta.tagline:
        parts.append(f"Tagline: {meta.tagline}")
    if meta.premise:
        parts.append(f"Premise:\n{meta.premise}")
    if meta.world_primer:
        parts.append(f"World primer:\n{meta.world_primer}")
    return "\n\n".join(parts)


def _propose_blueprint(
    db: Session,
    brief: str,
    docs_overview: str | None,
    *,
    n_chars: int,
    n_settings: int,
) -> tuple[list[ProposedStat], list[str], list[str]]:
    base_url, api_key, model, params = resolve_llm(db)
    counts = (
        f"\nPropose {_DEFAULT_STATS} stats, {max(1, n_chars)} character concepts, "
        f"and {max(1, n_settings)} setting concepts."
    )
    system = _BLUEPRINT_SYSTEM + counts
    user = f"World brief:\n{brief}{docs_block(docs_overview)}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    data = extract_json(llm.chat_complete(base_url, api_key, model, messages, gen_params(params)))

    taken: set[str] = set()
    stats: list[ProposedStat] = []
    raw_stats = data.get("stats")
    for row in raw_stats if isinstance(raw_stats, list) else []:
        stat = _sanitize_stat(row, taken)
        if stat is not None:
            stats.append(stat)
        if len(stats) >= MAX_STATS:
            break

    def _concepts(value: object, limit: int) -> list[str]:
        rows = value if isinstance(value, list) else []
        out = [str(v).strip() for v in rows if str(v).strip()]
        return out[:limit]

    characters = _concepts(data.get("characters"), n_chars)
    settings = _concepts(data.get("settings"), n_settings)
    return stats, characters, settings


def validate_build_inputs(
    db: Session, seed: str | None, docs_overview: str | None
) -> tuple[str, str | None]:
    """Pre-flight: require context + a configured LLM; return (seed, docs).

    Called before the stream opens (so missing-context / unconfigured-LLM return a
    normal ``400`` rather than an in-band error event), and again at the top of
    ``iter_build_world`` (idempotent — both are cheap settings reads).
    """
    seed = (seed or "").strip()
    docs = (docs_overview or "").strip()[:DOCS_CAP] or None
    if not seed and not docs:
        raise APIError(
            400,
            "bad_request",
            "Provide context to build from — a one-sentence seed or dropped reference files.",
        )
    # Resolve the LLM up front so an unconfigured model fails fast (before drafting).
    resolve_llm(db)
    return seed, docs


def iter_build_world(
    db: Session,
    seed: str | None,
    docs_overview: str | None = None,
    storyline_id: str | None = None,
    *,
    max_characters: int | None = None,
    max_settings: int | None = None,
) -> Iterator[BuildEvent]:
    """Draft a whole world, yielding a progress event at each stage.

    The live backbone for the New Storyline page: storyline metadata → World Primer
    → blueprint (stat schema + cast/setting concepts) → one full character per
    concept → one full setting per concept → a terminal ``done`` carrying the
    assembled ``ProposedWorld``. Errors propagate (the route wraps them into an
    in-band ``error`` event once the stream is open).
    """
    seed, docs_overview = validate_build_inputs(db, seed, docs_overview)
    effective_seed = seed or _DOCS_ONLY_SEED

    # 1) Storyline metadata.
    yield BuildStatusEvent(stage="metadata", message="Drafting the title, genre, and premise…")
    meta = storyline_agent.draft_storyline(db, effective_seed, docs_overview)
    yield BuildMetaEvent(
        title=meta.title, genre=meta.genre, tagline=meta.tagline, premise=meta.premise
    )

    # 2) World Primer.
    yield BuildStatusEvent(stage="primer", message="Writing the World Primer…")
    primer = storyline_agent.generate_world_primer(db, meta.premise, effective_seed, docs_overview)
    yield BuildPrimerEvent(world_primer=primer)
    storyline = ProposedStoryline(
        title=meta.title,
        genre=meta.genre,
        tagline=meta.tagline,
        premise=meta.premise,
        world_primer=primer,
    )

    n_chars = _clamp_count(max_characters, _DEFAULT_CHARACTERS, MAX_CHARACTERS)
    n_settings = _clamp_count(max_settings, _DEFAULT_SETTINGS, MAX_SETTINGS)

    # 3) Blueprint: the stat schema + character/setting concepts.
    yield BuildStatusEvent(stage="blueprint", message="Designing the stat schema and the cast…")
    brief = _world_brief(storyline)
    stats, char_concepts, setting_concepts = _propose_blueprint(
        db, brief, docs_overview, n_chars=n_chars, n_settings=n_settings
    )
    yield BuildPlanEvent(stats=stats, characters=char_concepts, settings=setting_concepts)

    # Ground each entity draft in the just-drafted world (it has no DB row yet, so the
    # brief travels inline as reference text alongside any author-provided docs).
    grounding = brief if not docs_overview else f"{brief}\n\n{docs_overview}"
    grounding = grounding[:DOCS_CAP]
    default_stats = [ProposedStartingStat(key=s.key, value=s.default) for s in stats]

    # 4) One full character per concept (+ schema-default starting stats).
    characters: list[ProposedCharacter] = []
    for i, concept in enumerate(char_concepts):
        yield BuildStatusEvent(
            stage="characters",
            message=f"Drafting character {i + 1} of {len(char_concepts)}…",
        )
        draft = character_agent.draft_character(db, concept, grounding, None)
        character = ProposedCharacter(**draft.model_dump(), starting_stats=list(default_stats))
        characters.append(character)
        yield BuildCharacterEvent(index=i, total=len(char_concepts), character=character)

    # 5) One full setting per concept.
    settings: list[ProposedSetting] = []
    for i, concept in enumerate(setting_concepts):
        yield BuildStatusEvent(
            stage="settings",
            message=f"Drafting setting {i + 1} of {len(setting_concepts)}…",
        )
        setting_draft = setting_agent.draft_setting(db, concept, grounding, None)
        setting = ProposedSetting(**setting_draft.model_dump())
        settings.append(setting)
        yield BuildSettingEvent(index=i, total=len(setting_concepts), setting=setting)

    yield BuildDoneEvent(
        world=ProposedWorld(
            storyline=storyline, stats=stats, characters=characters, settings=settings
        )
    )


def build_world(
    db: Session,
    seed: str | None,
    docs_overview: str | None = None,
    storyline_id: str | None = None,
    *,
    max_characters: int | None = None,
    max_settings: int | None = None,
) -> ProposedWorld:
    """Draft an entire world for review — the non-streaming collector.

    Drains ``iter_build_world`` and returns the assembled ``ProposedWorld`` from its
    terminal ``done`` event. Errors propagate unchanged (the generator does not
    swallow them), so the ``/build`` route keeps its existing 4xx/5xx behaviour.
    """
    world: ProposedWorld | None = None
    for event in iter_build_world(
        db,
        seed,
        docs_overview,
        storyline_id,
        max_characters=max_characters,
        max_settings=max_settings,
    ):
        if isinstance(event, BuildDoneEvent):
            world = event.world
    assert world is not None  # iter_build_world always emits `done` on success
    return world
