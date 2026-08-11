"""World population — draft and persist a new world's starting cast and places.

The create-time phase that fills a freshly-committed storyline. It plans a roster
(``agents.roster_agent``), then drafts every entry through the *same* agents the
by-hand creators use (``character_agent.draft_character`` /
``setting_agent.draft_setting``) and persists each one through ``services.crud`` —
so a populated world is indistinguishable from a hand-authored one and picks up the
same graph + RAG sync for free.

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

from app.agents import character_agent, roster_agent, setting_agent
from app.core.errors import APIError
from app.schemas.character import CharacterCreate
from app.schemas.setting import SettingCreate
from app.schemas.world_populate import (
    PopulateDoneFrame,
    PopulateEntityFrame,
    PopulateErrorFrame,
    PopulateEvent,
    PopulateStatusFrame,
    RosterEntry,
)
from app.services import comfyui, crud, portraits, scene_art, settings_store
from app.services import stats as stat_service


def _seed_of(entry: RosterEntry) -> str:
    """The one-line brief handed to the drafting agent."""
    return f"{entry.name} — {entry.seed}" if entry.seed else entry.name


def _message_of(exc: Exception) -> str:
    return exc.message if isinstance(exc, APIError) else str(exc) or exc.__class__.__name__


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
            char = crud.create_character(
                db,
                storyline_id,
                CharacterCreate(
                    name=draft.name or entry.name,
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
            setting = crud.create_setting(
                db,
                storyline_id,
                SettingCreate(
                    name=draft.name or entry.name,
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


def populate_world(
    db: Session,
    storyline_id: str,
    *,
    docs_overview: str | None = None,
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

    yield PopulateStatusFrame(stage="roster", message="Planning the cast and places…")
    roster = roster_agent.propose_roster(
        db,
        storyline_id=storyline_id,
        docs_overview=docs_overview,
        max_characters=max_characters,
        max_settings=max_settings,
    )

    artwork, artwork_note = _artwork_enabled(db, with_artwork)
    if artwork_note:
        yield PopulateErrorFrame(message=artwork_note)

    # The counts in the terminal frame are the entities that actually landed — one
    # `entity` frame each — so a run with failures reports what the author really got.
    made = {"character": 0, "setting": 0}
    stages = (
        _populate_characters(
            db, storyline_id, roster.characters, docs_overview=docs_overview, artwork=artwork
        ),
        _populate_settings(
            db, storyline_id, roster.settings, docs_overview=docs_overview, artwork=artwork
        ),
    )
    for stage in stages:
        for event in stage:
            if isinstance(event, PopulateEntityFrame):
                made[event.stage] += 1
            yield event

    yield PopulateDoneFrame(characters=made["character"], settings=made["setting"])
