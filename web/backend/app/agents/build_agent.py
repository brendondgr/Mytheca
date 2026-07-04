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

from app.agents import character_agent, extract_agent, setting_agent, storyline_agent
from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    DOCS_CAP,
    LlmConn,
    docs_block,
    extract_json,
    gen_params,
    resolve_llm,
)
from app.core.errors import APIError
from app.schemas.build import (
    MAX_CHARACTERS,
    MAX_SETTINGS,
    MAX_STATS,
    BuildCharacterEvent,
    BuildDoc,
    BuildDoneEvent,
    BuildEvent,
    BuildMetaEvent,
    BuildPlanEvent,
    BuildPrimerEvent,
    BuildSettingEvent,
    BuildStatusEvent,
    ExtractedEntities,
    ExtractedEntity,
    ProposedCharacter,
    ProposedSetting,
    ProposedStartingStat,
    ProposedStat,
    ProposedStoryline,
    ProposedWorld,
)
from app.schemas.stat import StatBand
from app.services import concurrency, llm, settings_store

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
    'the form {"stats": [{"displayName": "Stamina", "description": "{Character}\'s '
    "capacity for sustained physical and magical exertion. Lower values mean "
    "{Character} is tired and can do less; higher values mean they have the energy "
    'to act.", "min": 0, "max": 100, "default": 100, "bands": [{"min": 0, "max": 20, '
    '"label": "Exhausted", "description": "{Character} is exhausted and cannot act at '
    'their former strength."}, {"min": 81, "max": 100, "label": "Vigorous", '
    '"description": "{Character} is full of energy and has the drive to do whatever '
    'they set their mind to."}]}], '
    '"characters": ["one vivid sentence describing a character", ...], "settings": '
    '["one vivid sentence describing a place", ...]}.\n'
    "Every stat description MUST be 1-2 sentences that use the literal placeholder "
    "{Character} (never a real name) and explain what LOW vs HIGH values mean. Each "
    "stat needs 2-4 labeled bands; every band needs a 1-sentence description, also "
    "using the {Character} placeholder, saying what the character is like in that "
    "range. At play time {Character} is replaced with the acting character's name, so "
    "write descriptions that read naturally with a name substituted in. Each cast/"
    "setting concept is a single sentence a downstream agent will flesh out. Keep "
    "everything consistent with the world brief."
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
        description = str(row.get("description") or "").strip()
        bands.append(StatBand(min=bmin, max=bmax, label=label, description=description))
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
    # Backend-set thinking budget for the build. The per-entity character/setting/
    # storyline drafts below inherit the same DEFAULT_AUTHORING_EFFORT from their
    # standalone agents — none of it is user-controllable.
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params),
            reasoning=DEFAULT_AUTHORING_EFFORT,
        )
    )

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


def _doc_sources(docs: list[BuildDoc] | None, cap: int | None = None) -> list[tuple[str, str]]:
    """Turn attached character/setting docs into ``(label, source-text)`` pairs.

    ``label`` is the doc name (shown on the skeleton card); ``source-text`` is the
    doc body fed to the draft agent as the entity's source. Blank docs are skipped.
    By default there is **no cap** — every attached doc becomes an entity (the author
    asked for exactly these); pass ``cap`` only to bound a specific call.
    """
    out: list[tuple[str, str]] = []
    for d in docs or []:
        text = (d.text or "").strip()
        if not text:
            continue
        label = (d.name or "").strip() or text[:60]
        out.append((label, text[:DOCS_CAP]))
        if cap is not None and len(out) >= cap:
            break
    return out


def has_buildable_docs(*lists: list[BuildDoc] | None) -> bool:
    """True if any attached reference doc carries text to build from."""
    return any((d.text or "").strip() for docs in lists for d in (docs or []))


def _dedup(entities: list[ExtractedEntity], seen: set[str]) -> list[ExtractedEntity]:
    """Append entities not already seen (folded-name key); first occurrence wins."""
    out: list[ExtractedEntity] = []
    for e in entities:
        key = e.name.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _extract_one(
    db: Session, conn: LlmConn, name: str, text: str, grounding: str, *, kind: str
) -> ExtractedEntities:
    """Extract one doc's entities with a single retry (for the concurrent build loop).

    Runs on a worker thread with the pre-resolved ``conn`` (``extract_entities`` uses
    it via ``resolve_llm_or`` and never touches ``db`` — same Session-safety contract
    as the per-entity draft closures). ``kind`` scopes the extraction to the doc's
    triage bucket. A malformed-JSON reply (or a transient upstream error) is retried
    **once**, since LOW-effort extraction usually succeeds on the retry; a second
    failure raises, and ``imap_unordered`` isolates it.
    """
    try:
        return extract_agent.extract_entities(db, text, grounding, doc_name=name, conn=conn, kind=kind)
    except APIError:
        return extract_agent.extract_entities(db, text, grounding, doc_name=name, conn=conn, kind=kind)


def _fallback_entity(name: str, text: str) -> ExtractedEntity:
    """The whole document as ONE entity — used when a doc the author *classified* as a
    character/setting yields no explicitly named subject (its classification asserts it
    is one, so it is never lost). The draft agent overrides the provisional name."""
    label = re.sub(r"\.(md|markdown|txt|text)$", "", name.strip(), flags=re.IGNORECASE)
    return ExtractedEntity(name=label or "Unnamed", source=text[:DOCS_CAP])


def _collect_roster(
    jobs: list[tuple[str, str, str]],
    found_slots: list[ExtractedEntities | None],
) -> tuple[list[ExtractedEntity], list[ExtractedEntity]]:
    """Fold per-doc extraction results into the roster **in document order**, honoring
    each doc's kind and the classified fallback.

    * ``character`` / ``setting`` job → take only that kind; if the doc produced no
      named subject (extraction empty *or* unreadable), fall back to **one** entity from
      the whole doc (the author classified it, so it is guaranteed ≥1).
    * ``both`` (uncategorized) job → take whatever named subjects were found, and
      **nothing** if none (0 is a valid, expected result — no invention).

    De-dup is by folded name in document order (first occurrence wins), uncapped.
    """
    characters: list[ExtractedEntity] = []
    settings: list[ExtractedEntity] = []
    seen_chars: set[str] = set()
    seen_settings: set[str] = set()
    for (name, text, kind), found in zip(jobs, found_slots):
        found_chars = found.characters if found else []
        found_settings = found.settings if found else []
        if kind == "character":
            # Fall back to one entity ONLY when the doc named NOTHING (empty extraction
            # or unreadable) — not when its subject was already counted from another doc
            # (that would spuriously invent a filename-named duplicate).
            if not found_chars:
                found_chars = [_fallback_entity(name, text)]
            characters.extend(_dedup(found_chars, seen_chars))
        elif kind == "setting":
            if not found_settings:
                found_settings = [_fallback_entity(name, text)]
            settings.extend(_dedup(found_settings, seen_settings))
        else:  # uncategorized — strict, may contribute nothing (no fallback)
            characters.extend(_dedup(found_chars, seen_chars))
            settings.extend(_dedup(found_settings, seen_settings))
    return characters, settings


def validate_build_inputs(
    db: Session,
    seed: str | None,
    docs_overview: str | None,
    *,
    has_entity_docs: bool = False,
) -> tuple[str, str | None]:
    """Pre-flight: require context + a configured LLM; return (seed, docs).

    Called before the stream opens (so missing-context / unconfigured-LLM return a
    normal ``400`` rather than an in-band error event), and again at the top of
    ``iter_build_world`` (idempotent — both are cheap settings reads). Attached
    character/setting docs count as context too (you can build from them alone).
    """
    seed = (seed or "").strip()
    docs = (docs_overview or "").strip()[:DOCS_CAP] or None
    if not seed and not docs and not has_entity_docs:
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
    character_docs: list[BuildDoc] | None = None,
    setting_docs: list[BuildDoc] | None = None,
    uncategorized_docs: list[BuildDoc] | None = None,
    other_docs: list[BuildDoc] | None = None,
) -> Iterator[BuildEvent]:
    """Draft a whole world, yielding a progress event at each stage.

    The live backbone for the New Storyline page: storyline metadata → World Primer
    → blueprint (stat schema) → **extract entities, respecting the author's triage
    bucket** → one full character/setting per extracted subject → a terminal ``done``
    carrying the assembled ``ProposedWorld``.

    **Cast/settings come ONLY from the attached, triaged docs, and extraction respects
    the author's classification** — it never invents a subject by expanding lore:

    * ``character_docs`` → mine for explicitly NAMED characters only; usually exactly
      one (the doc *is* that character), split into several only when it clearly names
      several. A doc that yields no explicit name still becomes **one** character (the
      classification asserts it is one).
    * ``setting_docs`` → the same, for named settings.
    * ``uncategorized_docs`` → read carefully; produce an entity **only if a genuinely
      NAMED** character/setting is present. A lore/history/rules/atmosphere doc yields
      **nothing**.
    * ``other_docs`` → **lore/grounding only**; never become entities (their text folds
      into the drafting grounding so drafts stay consistent with them).

    Subjects are de-duped across docs in document order (uncapped). The build never
    invents an entity the author didn't attach: no entity docs → no cast/settings.
    (The storyline metadata, World Primer, and the universal stat schema are always
    produced.) Errors propagate (the route wraps them into an in-band ``error`` event
    once the stream is open).
    """
    seed, docs_overview = validate_build_inputs(
        db,
        seed,
        docs_overview,
        has_entity_docs=has_buildable_docs(
            character_docs, setting_docs, uncategorized_docs, other_docs
        ),
    )
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

    # 3) Blueprint: the universal stat schema. (It also returns invented cast/setting
    #    concepts, which we deliberately ignore — the cast/settings come only from the
    #    attached docs below.)
    yield BuildStatusEvent(stage="blueprint", message="Designing the stat schema…")
    brief = _world_brief(storyline)
    stats, _, _ = _propose_blueprint(
        db, brief, docs_overview, n_chars=n_chars, n_settings=n_settings
    )

    # Ground each draft in the just-drafted world (it has no DB row yet, so the brief
    # travels inline as reference text alongside any author-provided docs). **Other**-
    # bucket docs are lore/grounding only — they never become entities, but they DO fold
    # into the grounding here so drafts stay consistent with them.
    other_lore = "\n\n".join(text for _, text in _doc_sources(other_docs))
    grounding = "\n\n".join(p for p in (brief, docs_overview, other_lore) if p)[:DOCS_CAP]

    # Concurrency for extraction + the per-entity drafts. Pre-resolve the LLM
    # connection ONCE on this (request) thread and hand it to each worker via ``conn=``
    # so the worker threads never touch the request Session (world_context/rag_block
    # are no-ops for a None storyline_id — see agents/_common). ``authoringConcurrency``
    # (Options) bounds the pool; 1 keeps it fully sequential for single-slot backends.
    # Image generation is unaffected (it stays sequential on the frontend).
    conn = resolve_llm(db)
    workers = settings_store.get_llm(db).authoring_concurrency

    # 4) Extract the roster, **respecting the author's classification**. Each doc is
    #    mined only for the kind its bucket asserts — character docs for named
    #    characters, setting docs for named settings, uncategorized docs for either;
    #    Other docs are lore only (already folded into ``grounding`` above, never
    #    extracted). Runs **concurrently** (bounded by ``workers``), **failure-isolated**
    #    (``imap_unordered`` → skip on a second parse/upstream failure so one malformed
    #    reply can't abort the whole build), with a **per-doc status** so the UI shows
    #    movement instead of freezing on a single "Reading docs…" line.
    extract_jobs: list[tuple[str, str, str]] = (  # (name, text, kind)
        [(n, t, "character") for n, t in _doc_sources(character_docs)]
        + [(n, t, "setting") for n, t in _doc_sources(setting_docs)]
        + [(n, t, "both") for n, t in _doc_sources(uncategorized_docs)]
    )
    total_docs = len(extract_jobs)
    yield BuildStatusEvent(
        stage="extract",
        message=(
            f"Reading {total_docs} document(s) for named characters and settings…"
            if total_docs
            else "Reading your documents for named characters and settings…"
        ),
    )
    found_slots: list[ExtractedEntities | None] = [None] * total_docs
    unparsed: list[str] = []
    read = 0
    extract_thunks = [
        (lambda n=n, t=t, k=k: _extract_one(db, conn, n, t, grounding, kind=k))
        for n, t, k in extract_jobs
    ]
    for i, found in concurrency.imap_unordered(extract_thunks, max_workers=workers):
        read += 1
        name, _, kind = extract_jobs[i]
        if found is None:
            # A classified (character/setting) doc still becomes one entity via the
            # fallback in _collect_roster; only an uncategorized doc is truly dropped.
            if kind == "both":
                unparsed.append(name)
        else:
            found_slots[i] = found
        note = f" · {len(unparsed)} unreadable" if unparsed else ""
        yield BuildStatusEvent(stage="extract", message=f"Read {read}/{total_docs}: {name}{note}")
    if unparsed:
        shown = ", ".join(unparsed[:5]) + ("…" if len(unparsed) > 5 else "")
        yield BuildStatusEvent(
            stage="extract",
            message=(
                f"{len(unparsed)} uncategorized document(s) couldn't be read and were "
                f"skipped ({shown})."
            ),
        )
    char_entities, setting_entities = _collect_roster(extract_jobs, found_slots)
    yield BuildPlanEvent(
        stats=stats,
        characters=[e.name for e in char_entities],
        settings=[e.name for e in setting_entities],
    )

    default_stats = [ProposedStartingStat(key=s.key, value=s.default) for s in stats]

    # 5) One full character per extracted subject, drafted concurrently (voice samples
    #    included, before the schema-default starting stats). Events stream out of
    #    order as each completes — the New Storyline page places them by ``index``.
    def _draft_character(entity: ExtractedEntity) -> ProposedCharacter:
        draft = character_agent.draft_character(db, entity.source, grounding, None, conn=conn)
        voice = character_agent.propose_voice_samples(
            db,
            name=draft.name,
            role=draft.role,
            traits=draft.traits,
            speech=draft.speech,
            background=draft.background,
            personality=draft.personality,
            conn=conn,
        )
        return ProposedCharacter(
            **draft.model_dump(),
            voice_samples=voice.samples,
            starting_stats=list(default_stats),
        )

    char_slots: list[ProposedCharacter | None] = [None] * len(char_entities)
    if char_entities:
        yield BuildStatusEvent(
            stage="characters", message=f"Drafting {len(char_entities)} character(s)…"
        )
    char_thunks = [(lambda e=e: _draft_character(e)) for e in char_entities]
    for i, character in concurrency.imap_unordered(char_thunks, max_workers=workers):
        # Best-effort per entity: a single failed draft is skipped, never fatal (the
        # metadata/primer/blueprint drafts already ran, so the LLM is known-reachable).
        if character is None:
            continue
        char_slots[i] = character
        yield BuildCharacterEvent(index=i, total=len(char_entities), character=character)
    characters = [c for c in char_slots if c is not None]

    # 6) One full setting per extracted subject, drafted concurrently.
    def _draft_setting(entity: ExtractedEntity) -> ProposedSetting:
        setting_draft = setting_agent.draft_setting(db, entity.source, grounding, None, conn=conn)
        return ProposedSetting(**setting_draft.model_dump())

    setting_slots: list[ProposedSetting | None] = [None] * len(setting_entities)
    if setting_entities:
        yield BuildStatusEvent(
            stage="settings", message=f"Drafting {len(setting_entities)} setting(s)…"
        )
    setting_thunks = [(lambda e=e: _draft_setting(e)) for e in setting_entities]
    for i, setting in concurrency.imap_unordered(setting_thunks, max_workers=workers):
        if setting is None:
            continue
        setting_slots[i] = setting
        yield BuildSettingEvent(index=i, total=len(setting_entities), setting=setting)
    settings = [s for s in setting_slots if s is not None]

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
    character_docs: list[BuildDoc] | None = None,
    setting_docs: list[BuildDoc] | None = None,
    uncategorized_docs: list[BuildDoc] | None = None,
    other_docs: list[BuildDoc] | None = None,
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
        character_docs=character_docs,
        setting_docs=setting_docs,
        uncategorized_docs=uncategorized_docs,
        other_docs=other_docs,
    ):
        if isinstance(event, BuildDoneEvent):
            world = event.world
    assert world is not None  # iter_build_world always emits `done` on success
    return world
