"""World population — draft and persist a new world's starting cast and places.

The create-time phase that fills a freshly-committed storyline. **The author's own
files come first**: every context document they classified as Characters or Settings
is mined by ``agents.extract_agent`` for the subjects it explicitly names, and the
build makes exactly those — one entity per subject, drafted from that document's own
text and linked back to it. ``other``-bucket files are lore: they ground every draft
and become nothing. Only a world with no such files (or an author who explicitly asks)
gets an invented roster from ``agents.roster_agent``.

Each entry is then built through the *same* agents the by-hand creators use
(``character_agent.draft_character`` / ``setting_agent.draft_setting``) and persisted
through ``services.crud`` — so a populated world is indistinguishable from a
hand-authored one and picks up the same graph + RAG sync for free.

Two failure postures, deliberately different:

* **The roster is fatal.** Without it there is nothing to build, so an unconfigured
  LLM or an unparseable proposal aborts the run (a terminal ``error`` frame).
* **Every entity is not.** One failed draft, one failed render, costs that one item:
  an ``error`` frame is emitted and the run continues. A world is never rolled back —
  a partially populated world is strictly better than an empty one, and the author
  can add the rest by hand.

Artwork is opt-in *and* gated on ComfyUI actually being configured; each image is a
full render, so it is never on by default and never blocks an entity from existing.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents import character_agent, extract_agent, roster_agent, setting_agent
from app.agents._common import resolve_llm
from app.core.errors import APIError
from app.schemas.character import CharacterCreate
from app.schemas.setting import SettingCreate
from app.schemas.world_populate import (
    PopulateDoneFrame,
    PopulatePlanFrame,
    PopulateEntityFrame,
    PopulateErrorFrame,
    PopulateEvent,
    PopulateStatusFrame,
    RosterEntry,
)
from app.services import comfyui, concurrency, crud, portraits, scene_art, settings_store
from app.services import stats as stat_service


def _seed_of(entry: RosterEntry) -> str:
    """The brief handed to the drafting agent.

    For an entry taken from one of the author's files that is the paragraph the
    extractor drew from it — so the character written is *their* character, not a
    fresh invention that merely shares a name.
    """
    if entry.source:
        return f"{entry.name}\n\n{entry.source}"
    return f"{entry.name} — {entry.seed}" if entry.seed else entry.name


def _message_of(exc: Exception) -> str:
    return exc.message if isinstance(exc, APIError) else str(exc) or exc.__class__.__name__


def _unique_name(taken: set[str], drafted: str, proposed: str, qualifier: str = "") -> str:
    """A name no other entity in this world already has.

    The roster de-duplicates the names it *proposes*, but each draft agent invents its
    own name from the seed and two of them can land on the same one — a real run
    produced two separate characters called "Kaelen Thorne". Duplicate names are not
    cosmetic here: the turn loop resolves speakers and relationships **by name**, so a
    collision makes two characters indistinguishable to the engine.

    Preference order: the drafted name, then the name the roster proposed, then the
    drafted name qualified by its role/type, then a numeric suffix as the backstop.
    """
    candidates = [drafted, proposed]
    if qualifier:
        candidates.append(f"{drafted} ({qualifier})")
    for candidate in candidates:
        if candidate and candidate.casefold() not in taken:
            return candidate
    base = drafted or proposed
    n = 2
    while f"{base} {n}".casefold() in taken:
        n += 1
    return f"{base} {n}"


# ---- where the roster comes from -------------------------------------------


def _storyline_docs(db: Session, storyline_id: str) -> list:
    """The world's storyline-level corpus (entity-scoped docs belong to an entity)."""
    return [
        d
        for d in crud.list_context_documents(db, storyline_id)
        if not d.entity_type and (d.content or "").strip()
    ]


def _sort_sources(docs: list) -> tuple[list, list, list, list]:
    """Split the corpus into (character, setting, mine-either, lore) documents.

    The author's **classification is the opt-in**: a file they (or Triage) put in the
    Characters bucket is a character source, full stop — asking for a second per-file
    checkbox is the friction that made the build ignore their uploads in the first
    place. ``other`` is lore: it grounds the drafts and yields no entities.

    The one nuance: an untriaged corpus persists entirely as ``other`` (the wire schema
    has no "uncategorized"), and treating a world whose every file is unclassified as
    "all lore, build nothing" would silently ignore the uploads. So when *nothing* is
    classified, every file is mined for either kind.
    """
    characters = [d for d in docs if d.category == "character"]
    settings = [d for d in docs if d.category == "setting"]
    rest = [d for d in docs if d.category not in ("character", "setting")]
    if not characters and not settings:
        return [], [], rest, []
    return characters, settings, [], rest


def _entries_from(found, docs: list, kind: str) -> list[RosterEntry]:
    """Extracted subjects → roster entries, tagged with the file they came from."""
    entries: list[RosterEntry] = []
    for doc, entities in zip(docs, found, strict=True):
        subjects = [] if entities is None else getattr(entities, kind)
        for subject in subjects:
            entries.append(
                RosterEntry(
                    name=subject.name,
                    source=subject.source,
                    doc_id=doc.id,
                    doc_name=doc.name,
                )
            )
    return entries


def _fallback_entry(doc) -> RosterEntry:
    """A classified file that named nothing still becomes its own entity.

    The author put this file in the Characters (or Settings) bucket, so it is about
    somebody: dropping it because the extractor found no proper name would lose their
    upload — the exact failure this whole path exists to prevent.
    """
    return RosterEntry(
        name=doc.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
        or doc.name,
        source=(doc.content or "")[:4000],
        doc_id=doc.id,
        doc_name=doc.name,
    )


def _link_source(db: Session, entry: RosterEntry, entity_type: str, entity_id: str) -> None:
    """Record which of the author's files an entity came from (best-effort)."""
    if not entry.doc_id:
        return
    try:
        crud.add_document_link(db, entry.doc_id, entity_type, entity_id)
    except Exception:  # provenance is a nicety; never cost the entity over it
        db.rollback()


def _artwork_enabled(db: Session, requested: bool) -> tuple[bool, str | None]:
    """Whether artwork can actually be rendered, plus why not when it cannot.

    The stored ComfyUI base URL always has a default, so "configured" proves nothing —
    the gate is one cheap reachability probe up front. Failing here once beats letting
    every entity wait out its own render timeout.
    """
    if not requested:
        return False, None
    base = settings_store.resolve_comfy_base_url(db, None)
    if not base:
        return False, "ComfyUI is not configured — the world was built without artwork."
    try:
        comfyui.check_connection(base)
    except Exception:
        return False, f"ComfyUI is not reachable at {base} — the world was built without artwork."
    return True, None


def _write_voice(db: Session, char) -> str | None:
    """Best-effort voice & tone profile for a persisted character. Returns an error.

    Runs *before* the starting stats, matching the order the retired world build used:
    a character's voice is derived from their prose, and the stats are keyed to who
    they turn out to be.
    """
    try:
        voice = character_agent.propose_voice_samples(
            db,
            name=char.name,
            role=char.role,
            traits=char.traits,
            speech=char.speech,
            background=char.background,
            personality=char.personality,
            storyline_id=char.storyline_id,
        )
        if not voice.samples:
            return None
        char.voice_samples = [s.model_dump() for s in voice.samples]
        db.commit()
        return None
    except Exception as exc:  # a voiceless character is still a character
        db.rollback()
        return f"Could not find {char.name}'s voice: {_message_of(exc)}"


def _write_starting_stats(db: Session, char) -> str | None:
    """Best-effort starting stat values keyed to the world's schema. Returns an error.

    A world with no stat definitions costs nothing — ``propose_starting_stats`` makes
    no LLM call and returns no proposals.
    """
    try:
        proposal = character_agent.propose_starting_stats(
            db,
            char.storyline_id,
            name=char.name,
            role=char.role,
            traits=char.traits,
            personality=char.personality,
            background=char.background,
        )
        values = {p.key: p.value for p in proposal.proposals}
        if not values:
            return None
        stat_service.set_character_stats(db, char.id, values)
        return None
    except Exception as exc:
        db.rollback()
        return f"Could not set {char.name}'s starting stats: {_message_of(exc)}"


def _render_portrait(db: Session, char) -> tuple[str | None, str | None]:
    """Best-effort portrait for a persisted character. Returns ``(url, error)``."""
    try:
        prompts = character_agent.generate_portrait_prompts(
            db,
            name=char.name,
            role=char.role,
            appearance=char.appearance,
            traits=char.traits,
        )
        result = portraits.generate_portrait(db, prompts.positive, prompts.negative)
        char.portrait = result["portrait"]
        char.portrait_positive = prompts.positive
        char.portrait_negative = prompts.negative
        db.commit()
        return char.portrait, None
    except Exception as exc:  # a failed render must never cost the character
        db.rollback()
        return None, f"Could not render a portrait for {char.name}: {_message_of(exc)}"


def _render_scene_art(db: Session, setting) -> tuple[str | None, str | None]:
    """Best-effort establishing shot for a persisted setting. Returns ``(url, error)``."""
    try:
        prompts = setting_agent.generate_scene_art_prompts(
            db,
            name=setting.name,
            type=setting.type,
            desc=setting.desc,
            atmosphere=setting.atmosphere,
            features=setting.features,
            current_state=setting.current_state,
        )
        result = scene_art.generate_scene_art(db, prompts.positive, prompts.negative)
        setting.image = result["image"]
        setting.scene_art_positive = prompts.positive
        setting.scene_art_negative = prompts.negative
        db.commit()
        return setting.image, None
    except Exception as exc:  # a failed render must never cost the setting
        db.rollback()
        return None, f"Could not render scene art for {setting.name}: {_message_of(exc)}"


def _populate_characters(
    db: Session,
    storyline_id: str,
    entries: list[RosterEntry],
    *,
    docs_overview: str | None,
    artwork: bool,
) -> Iterator[PopulateEvent]:
    """Draft + persist each cast member (one ``entity`` frame per one that landed)."""
    total = len(entries)
    # Names already spoken for in this world (pre-existing rows included, since a run
    # can be pointed at a world that is not empty).
    taken = {c.name.casefold() for c in crud.list_characters(db, storyline_id)}
    for index, entry in enumerate(entries, start=1):
        yield PopulateStatusFrame(
            stage="character",
            name=entry.name,
            index=index,
            total=total,
            message=f"Writing {entry.name}…",
        )
        try:
            draft = character_agent.draft_character(
                db, _seed_of(entry), docs_overview, storyline_id
            )
            name = _unique_name(taken, draft.name, entry.name, draft.role)
            char = crud.create_character(
                db,
                storyline_id,
                CharacterCreate(
                    name=name,
                    role=draft.role or "Character",
                    color=draft.color or "#8E2B1C",
                    traits=draft.traits,
                    speech=draft.speech,
                    goal=draft.goal,
                    secret=draft.secret,
                    appearance=draft.appearance,
                    background=draft.background,
                    personality=draft.personality,
                ),
            )
        except Exception as exc:
            yield PopulateErrorFrame(message=f"Could not write {entry.name}: {_message_of(exc)}")
            continue
        taken.add(char.name.casefold())
        _link_source(db, entry, "character", char.id)

        # The rest of the character, in the order the retired world build used: voice
        # from the prose, then stats keyed to who they turned out to be, then the
        # portrait. Each step is best-effort and announces itself so the author can
        # watch the character being finished rather than staring at one long pause.
        def _step(message: str, run) -> Iterator[PopulateEvent]:
            yield PopulateStatusFrame(
                stage="character", name=char.name, index=index, total=total, message=message
            )
            err = run()
            if err:
                yield PopulateErrorFrame(message=err)

        yield from _step(f"Finding {char.name}'s voice…", lambda: _write_voice(db, char))
        yield from _step(
            f"Setting {char.name}'s starting stats…", lambda: _write_starting_stats(db, char)
        )

        image = None
        if artwork:
            yield PopulateStatusFrame(
                stage="character",
                name=char.name,
                index=index,
                total=total,
                message=f"Painting {char.name}…",
            )
            image, err = _render_portrait(db, char)
            if err:
                yield PopulateErrorFrame(message=err)
        yield PopulateEntityFrame(
            stage="character", id=char.id, name=char.name, role=char.role, image=image
        )


def _populate_settings(
    db: Session,
    storyline_id: str,
    entries: list[RosterEntry],
    *,
    docs_overview: str | None,
    artwork: bool,
) -> Iterator[PopulateEvent]:
    """Draft + persist each place (one ``entity`` frame per one that landed)."""
    total = len(entries)
    taken = {s.name.casefold() for s in crud.list_settings(db, storyline_id)}
    for index, entry in enumerate(entries, start=1):
        yield PopulateStatusFrame(
            stage="setting",
            name=entry.name,
            index=index,
            total=total,
            message=f"Building {entry.name}…",
        )
        try:
            draft = setting_agent.draft_setting(db, _seed_of(entry), docs_overview, storyline_id)
            name = _unique_name(taken, draft.name, entry.name, draft.type)
            setting = crud.create_setting(
                db,
                storyline_id,
                SettingCreate(
                    name=name,
                    type=draft.type or "Social Hub",
                    desc=draft.desc or "A place yet to be described.",
                    atmosphere=draft.atmosphere,
                    features=draft.features,
                    current_state=draft.current_state,
                ),
            )
        except Exception as exc:
            yield PopulateErrorFrame(message=f"Could not build {entry.name}: {_message_of(exc)}")
            continue
        taken.add(setting.name.casefold())
        _link_source(db, entry, "setting", setting.id)

        image = None
        if artwork:
            yield PopulateStatusFrame(
                stage="setting",
                name=setting.name,
                index=index,
                total=total,
                message=f"Painting {setting.name}…",
            )
            image, err = _render_scene_art(db, setting)
            if err:
                yield PopulateErrorFrame(message=err)
        yield PopulateEntityFrame(
            stage="setting", id=setting.id, name=setting.name, role=setting.type, image=image
        )


def _read_documents(
    db: Session, storyline_id: str, docs: list
) -> Iterator[PopulateEvent | tuple]:
    """Mine the author's classified files for the subjects they name.

    Yields progress frames, then a terminal ``(characters, settings, lore, unreadable)``
    tuple. Extraction runs concurrently (bounded by ``authoringConcurrency``) with a
    pre-resolved LLM connection, so the worker threads never touch the request Session,
    and is failure-isolated per document.
    """
    char_docs, setting_docs, either_docs, lore_docs = _sort_sources(docs)
    jobs = (
        [(d, "character") for d in char_docs]
        + [(d, "setting") for d in setting_docs]
        + [(d, "both") for d in either_docs]
    )
    lore = "\n\n".join((d.content or "") for d in lore_docs)
    if not jobs:
        yield ([], [], lore, [])
        return

    conn = resolve_llm(db)
    workers = settings_store.get_llm(db).authoring_concurrency
    yield PopulateStatusFrame(
        stage="roster",
        total=len(jobs),
        message=f"Reading {len(jobs)} of your files for the people and places they name…",
    )

    found: list = [None] * len(jobs)
    read = 0
    thunks = [
        (
            lambda d=doc, k=kind: extract_agent.extract_entities(
                db, d.content or "", None, doc_name=d.name, kind=k, conn=conn
            )
        )
        for doc, kind in jobs
    ]
    for i, entities in concurrency.imap_unordered(thunks, max_workers=workers):
        read += 1
        found[i] = entities
        yield PopulateStatusFrame(
            stage="roster",
            index=read,
            total=len(jobs),
            name=jobs[i][0].name,
            message=f"Read {read}/{len(jobs)}: {jobs[i][0].name}",
        )

    docs_in_order = [doc for doc, _ in jobs]
    characters = _entries_from(found, docs_in_order, "characters")
    settings = _entries_from(found, docs_in_order, "settings")

    # A classified file that named nothing (or wouldn't parse) still becomes its own
    # entity — the author's upload is never silently dropped. An *unclassified* file
    # that names nothing is genuinely lore and yields nothing.
    unreadable: list[str] = []
    used = {e.doc_id for e in characters} | {e.doc_id for e in settings}
    for (doc, kind), entities in zip(jobs, found, strict=True):
        if doc.id in used:
            continue
        if entities is None:
            unreadable.append(doc.name)
        if kind == "character":
            characters.append(_fallback_entry(doc))
        elif kind == "setting":
            settings.append(_fallback_entry(doc))

    yield (characters, settings, lore, unreadable)


def _resolve_roster(
    db: Session,
    storyline_id: str,
    *,
    source: str,
    docs_overview: str | None,
    max_characters: int,
    max_settings: int,
) -> Iterator[PopulateEvent | tuple]:
    """Settle what will be built, and announce it. Yields frames then ``(plan, lore)``.

    Documents win: when the world has files the author classified as Characters or
    Settings, the build makes exactly those. Invention only happens when they asked for
    it, or when there is nothing else to go on.
    """
    docs = _storyline_docs(db, storyline_id) if source != "invent" else []

    characters: list[RosterEntry] = []
    settings: list[RosterEntry] = []
    lore = ""
    unreadable: list[str] = []
    if docs:
        for event in _read_documents(db, storyline_id, docs):
            if isinstance(event, tuple):
                characters, settings, lore, unreadable = event
            else:
                yield event

    used_documents = bool(characters or settings)
    note = ""
    if used_documents:
        note = f"Built from {len({e.doc_id for e in characters + settings})} of your files."
        if unreadable:
            shown = ", ".join(unreadable[:5]) + ("…" if len(unreadable) > 5 else "")
            note += f" {len(unreadable)} could not be read cleanly ({shown})."
    elif source == "documents":
        # Asked for documents and there are none to build from: say so and build
        # nothing rather than quietly inventing a cast the author never asked for.
        yield PopulateErrorFrame(
            message=(
                "No character or setting files to build from — classify some context "
                "files as Characters or Settings, or choose to invent a cast."
            )
        )
    else:
        yield PopulateStatusFrame(stage="roster", message="Inventing a cast and places…")
        invented = roster_agent.propose_roster(
            db,
            storyline_id=storyline_id,
            docs_overview=docs_overview,
            max_characters=max_characters,
            max_settings=max_settings,
        )
        characters, settings = invented.characters, invented.settings
        note = "Invented from the premise — no character or setting files were attached."

    resolved: str = "documents" if used_documents else "invent"
    yield PopulatePlanFrame(
        source=resolved, characters=characters, settings=settings, note=note
    )
    yield (characters, settings, lore)


def populate_world(
    db: Session,
    storyline_id: str,
    *,
    docs_overview: str | None = None,
    source: str = "auto",
    max_characters: int = 5,
    max_settings: int = 3,
    with_artwork: bool = False,
) -> Iterator[PopulateEvent]:
    """Plan, draft, and persist a new world's cast + places, streaming progress.

    Raises ``APIError`` before yielding anything for the fatal cases (unknown
    storyline, unconfigured LLM) so the route can answer with a normal error
    envelope instead of opening a stream it cannot fill.
    """
    crud.get_storyline(db, storyline_id)  # 404 pre-flight

    yield PopulateStatusFrame(stage="roster", message="Working out what to build…")
    characters: list[RosterEntry] = []
    settings: list[RosterEntry] = []
    lore = ""
    for event in _resolve_roster(
        db,
        storyline_id,
        source=source,
        docs_overview=docs_overview,
        max_characters=max_characters,
        max_settings=max_settings,
    ):
        if isinstance(event, tuple):
            characters, settings, lore = event
        else:
            yield event

    # Lore-bucket files never become entities, but they DO ground every draft so the
    # cast stays consistent with the world the author described.
    grounding = "\n\n".join(p for p in (docs_overview or "", lore) if p.strip()) or None

    artwork, artwork_note = _artwork_enabled(db, with_artwork)
    if artwork_note:
        yield PopulateErrorFrame(message=artwork_note)

    # The counts in the terminal frame are the entities that actually landed — one
    # `entity` frame each — so a run with failures reports what the author really got.
    made = {"character": 0, "setting": 0}
    stages = (
        _populate_characters(
            db, storyline_id, characters, docs_overview=grounding, artwork=artwork
        ),
        _populate_settings(db, storyline_id, settings, docs_overview=grounding, artwork=artwork),
    )
    for stage in stages:
        for event in stage:
            if isinstance(event, PopulateEntityFrame):
                made[event.stage] += 1
            yield event

    yield PopulateDoneFrame(characters=made["character"], settings=made["setting"])
