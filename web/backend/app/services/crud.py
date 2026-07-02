"""CRUD services for the four core objects.

Pure data operations over a SQLAlchemy session: id resolution (client-supplied or
generated), referential validation for a scenario's ``cast_ids``/``setting_id``,
``mono`` derivation, and ``position`` assignment so collections keep their order.
Routes stay thin; all integrity rules live here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.ids import new_hex_id, new_id
from app.models import Character, ContextDocument, Scenario, Setting, Storyline
from app.rag import indexer as rag_index
from app.services import graph_writer, settings_store
from app.schemas.character import CharacterCreate, CharacterUpdate
from app.schemas.context_document import (
    ContextDocumentCreate,
    ContextDocumentUpdate,
)
from app.schemas.scenario import ScenarioCreate, ScenarioUpdate
from app.schemas.setting import SettingCreate, SettingUpdate
from app.schemas.storyline import StorylineCreate, StorylineRead, StorylineUpdate

# ---- helpers ---------------------------------------------------------------


def _mono_of(name: str) -> str:
    """Port of the frontend ``monoOf`` so the backend owns the avatar monogram."""
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _next_position(db: Session, model: Any, storyline_id: str) -> int:
    count = db.scalar(
        select(func.count()).select_from(model).where(model.storyline_id == storyline_id)
    )
    return int(count or 0)


def _require_unique_id(db: Session, model: Any, given: str | None) -> None:
    if given and db.get(model, given) is not None:
        raise APIError(409, "conflict", f"{model.__name__} id '{given}' already exists.")


def _gen_hex_id(db: Session, model: Any, length: int) -> str:
    """Generate a bare hex id of ``length`` chars unused as ``model``'s PK.

    The 8-hex storyline space is huge, but the 4-hex scenario space is small
    enough (65 536) that a real collision is plausible once a world has many
    scenarios — so generation retries until the id is free, then widens by a
    char as a safety valve if the space is genuinely saturated.
    """
    for attempt in range(20):
        candidate = new_hex_id(length + attempt // 8)
        if db.get(model, candidate) is None:
            return candidate
    raise APIError(500, "id_exhausted", f"Could not allocate a free {model.__name__} id.")


def _validate_refs(
    db: Session, storyline_id: str, cast_ids: list[str] | None, setting_id: str | None
) -> None:
    bad = [
        cid
        for cid in (cast_ids or [])
        if (c := db.get(Character, cid)) is None or c.storyline_id != storyline_id
    ]
    if bad:
        raise APIError(422, "invalid_reference", "Unknown character id(s) in castIds.", {"castIds": bad})
    if setting_id:
        s = db.get(Setting, setting_id)
        if s is None or s.storyline_id != storyline_id:
            raise APIError(422, "invalid_reference", f"Unknown settingId '{setting_id}'.", {"settingId": setting_id})


# ---- storylines ------------------------------------------------------------


def list_storylines(db: Session) -> list[StorylineRead]:
    char_count = (
        select(func.count())
        .where(Character.storyline_id == Storyline.id)
        .correlate(Storyline)
        .scalar_subquery()
    )
    setting_count = (
        select(func.count())
        .where(Setting.storyline_id == Storyline.id)
        .correlate(Storyline)
        .scalar_subquery()
    )
    scenario_count = (
        select(func.count())
        .where(Scenario.storyline_id == Storyline.id)
        .correlate(Storyline)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            Storyline,
            char_count.label("character_count"),
            setting_count.label("setting_count"),
            scenario_count.label("scenario_count"),
        ).order_by(Storyline.position, Storyline.title)
    ).all()
    return [
        StorylineRead(
            id=row.Storyline.id,
            title=row.Storyline.title,
            genre=row.Storyline.genre,
            tagline=row.Storyline.tagline,
            premise=row.Storyline.premise,
            world_primer=row.Storyline.world_primer,
            symbol=row.Storyline.symbol,
            symbol_color=row.Storyline.symbol_color,
            character_count=row.character_count,
            setting_count=row.setting_count,
            scenario_count=row.scenario_count,
        )
        for row in rows
    ]


def get_storyline(db: Session, storyline_id: str) -> Storyline:
    sl = db.get(Storyline, storyline_id)
    if sl is None:
        raise APIError(404, "not_found", f"Storyline '{storyline_id}' not found.")
    return sl


def create_storyline(db: Session, data: StorylineCreate) -> Storyline:
    _require_unique_id(db, Storyline, data.id)
    sl = Storyline(
        id=data.id or _gen_hex_id(db, Storyline, 8),
        title=data.title,
        genre=data.genre,
        tagline=data.tagline,
        premise=data.premise,
        world_primer=data.world_primer,
        symbol=data.symbol,
        symbol_color=data.symbol_color,
        position=int(db.scalar(select(func.count()).select_from(Storyline)) or 0),
    )
    db.add(sl)
    db.commit()
    db.refresh(sl)
    rag_index.sync_storyline(sl)  # best-effort embed into the vector store
    return sl


def update_storyline(db: Session, storyline_id: str, data: StorylineUpdate) -> Storyline:
    sl = get_storyline(db, storyline_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sl, key, value)
    db.commit()
    db.refresh(sl)
    rag_index.sync_storyline(sl)  # best-effort re-embed into the vector store
    return sl


def delete_storyline(db: Session, storyline_id: str) -> None:
    db.delete(get_storyline(db, storyline_id))  # ORM cascade removes children
    db.commit()
    rag_index.remove_storyline(storyline_id)  # best-effort: drop the world's whole corpus


# ---- context documents (the persisted triaged RAG corpus) ------------------


def list_context_documents(
    db: Session,
    storyline_id: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> list[ContextDocument]:
    """List a world's context docs, optionally narrowed to one entity's scope.

    With no scope, returns every document (storyline-level + entity-scoped). With
    ``entity_type``/``entity_id`` it returns just that entity's docs — what a
    character/setting/scenario editor re-fetches so its files reappear."""
    get_storyline(db, storyline_id)
    stmt = select(ContextDocument).where(ContextDocument.storyline_id == storyline_id)
    if entity_type is not None and entity_id is not None:
        stmt = stmt.where(
            ContextDocument.entity_type == entity_type,
            ContextDocument.entity_id == entity_id,
        )
    return list(db.scalars(stmt.order_by(ContextDocument.position, ContextDocument.name)))


def _purge_entity_context_docs(db: Session, entity_type: str, entity_id: str) -> None:
    """Delete an entity's scoped context docs + their embeddings (delete cascade).

    Called from the character/setting/scenario delete paths so an entity's attached
    reference files don't outlive it in the corpus or the vector store."""
    docs = list(
        db.scalars(
            select(ContextDocument).where(
                ContextDocument.entity_type == entity_type,
                ContextDocument.entity_id == entity_id,
            )
        )
    )
    for doc in docs:
        db.delete(doc)
        rag_index.remove("context_document", doc.id)  # best-effort drop from the store


def get_context_document(db: Session, doc_id: str) -> ContextDocument:
    doc = db.get(ContextDocument, doc_id)
    if doc is None:
        raise APIError(404, "not_found", f"Context document '{doc_id}' not found.")
    return doc


def _new_context_document(
    db: Session, storyline_id: str, data: ContextDocumentCreate, position: int
) -> ContextDocument:
    _require_unique_id(db, ContextDocument, data.id)
    content = data.content or ""
    return ContextDocument(
        id=data.id or new_id("cd"),
        storyline_id=storyline_id,
        name=data.name,
        content=content,
        category=data.category,
        include_draft=data.include_draft,
        include_rag=data.include_rag,
        source=data.source,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        char_count=len(content),
        position=position,
    )


def create_context_document(
    db: Session, storyline_id: str, data: ContextDocumentCreate
) -> ContextDocument:
    get_storyline(db, storyline_id)
    doc = _new_context_document(
        db, storyline_id, data, _next_position(db, ContextDocument, storyline_id)
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    rag_index.sync_context_document(doc)  # best-effort embed
    return doc


def bulk_create_context_documents(
    db: Session, storyline_id: str, docs: list[ContextDocumentCreate]
) -> list[ContextDocument]:
    """Persist a whole triaged corpus in one transaction (the page commit)."""
    get_storyline(db, storyline_id)
    start = _next_position(db, ContextDocument, storyline_id)
    created = [
        _new_context_document(db, storyline_id, data, start + i)
        for i, data in enumerate(docs)
    ]
    db.add_all(created)
    db.commit()
    for doc in created:
        db.refresh(doc)
    # Embed the whole batch in parallel (bounded by the operator's authoringConcurrency),
    # best-effort — a slow/large corpus commit no longer blocks one embed at a time.
    rag_index.sync_context_documents(
        created, max_workers=settings_store.get_llm(db).authoring_concurrency
    )
    return created


def update_context_document(
    db: Session, doc_id: str, data: ContextDocumentUpdate
) -> ContextDocument:
    doc = get_context_document(db, doc_id)
    patch = data.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(doc, key, value)
    if "content" in patch:
        doc.char_count = len(doc.content or "")
    db.commit()
    db.refresh(doc)
    rag_index.sync_context_document(doc)  # re-embed (removes the point if include_rag was cleared)
    return doc


def delete_context_document(db: Session, doc_id: str) -> None:
    db.delete(get_context_document(db, doc_id))
    db.commit()
    rag_index.remove("context_document", doc_id)  # best-effort drop from the vector store


# ---- characters ------------------------------------------------------------


def list_characters(db: Session, storyline_id: str) -> list[Character]:
    get_storyline(db, storyline_id)
    return list(
        db.scalars(
            select(Character)
            .where(Character.storyline_id == storyline_id)
            .order_by(Character.position, Character.name)
        )
    )


def get_character(db: Session, character_id: str) -> Character:
    char = db.get(Character, character_id)
    if char is None:
        raise APIError(404, "not_found", f"Character '{character_id}' not found.")
    return char


def create_character(db: Session, storyline_id: str, data: CharacterCreate) -> Character:
    get_storyline(db, storyline_id)
    _require_unique_id(db, Character, data.id)
    char = Character(
        id=data.id or new_id("c"),
        storyline_id=storyline_id,
        name=data.name,
        role=data.role,
        color=data.color,
        mono=data.mono or _mono_of(data.name),
        traits=data.traits,
        speech=data.speech,
        goal=data.goal,
        secret=data.secret,
        appearance=data.appearance,
        background=data.background,
        personality=data.personality,
        portrait=data.portrait,
        portrait_positive=data.portrait_positive,
        portrait_negative=data.portrait_negative,
        voice_samples=[v.model_dump() for v in (data.voice_samples or [])],
        position=_next_position(db, Character, storyline_id),
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    graph_writer.sync_character(db, char)  # best-effort mirror into the Story Graph
    rag_index.sync_character(char)  # best-effort embed into the vector store
    return char


def update_character(db: Session, character_id: str, data: CharacterUpdate) -> Character:
    char = get_character(db, character_id)
    patch = data.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(char, key, value)
    if "name" in patch and "mono" not in patch:
        char.mono = _mono_of(char.name)
    db.commit()
    db.refresh(char)
    graph_writer.sync_character(db, char)  # best-effort mirror into the Story Graph
    rag_index.sync_character(char)  # best-effort re-embed
    return char


def delete_character(db: Session, character_id: str) -> None:
    char = get_character(db, character_id)
    storyline_id = char.storyline_id
    db.delete(char)
    # Mirror the frontend: drop the id from every scenario's cast in this storyline.
    for scenario in db.scalars(select(Scenario).where(Scenario.storyline_id == storyline_id)):
        if character_id in (scenario.cast_ids or []):
            scenario.cast_ids = [cid for cid in scenario.cast_ids if cid != character_id]
    _purge_entity_context_docs(db, "character", character_id)  # drop attached docs + embeddings
    db.commit()
    graph_writer.remove_node(character_id)  # best-effort removal from the Story Graph
    rag_index.remove("character", character_id)  # best-effort drop from the vector store


# ---- settings --------------------------------------------------------------


def list_settings(db: Session, storyline_id: str) -> list[Setting]:
    get_storyline(db, storyline_id)
    return list(
        db.scalars(
            select(Setting)
            .where(Setting.storyline_id == storyline_id)
            .order_by(Setting.position, Setting.name)
        )
    )


def get_setting(db: Session, setting_id: str) -> Setting:
    setting = db.get(Setting, setting_id)
    if setting is None:
        raise APIError(404, "not_found", f"Setting '{setting_id}' not found.")
    return setting


def create_setting(db: Session, storyline_id: str, data: SettingCreate) -> Setting:
    get_storyline(db, storyline_id)
    _require_unique_id(db, Setting, data.id)
    setting = Setting(
        id=data.id or new_id("s"),
        storyline_id=storyline_id,
        name=data.name,
        type=data.type,
        desc=data.desc,
        atmosphere=data.atmosphere,
        features=data.features,
        current_state=data.current_state,
        image=data.image,
        scene_art_positive=data.scene_art_positive,
        scene_art_negative=data.scene_art_negative,
        # Timeline is play-accrued (§4.1) — store an empty log at authoring, never None.
        timeline=[e.model_dump() for e in (data.timeline or [])],
        position=_next_position(db, Setting, storyline_id),
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    graph_writer.sync_setting(db, setting)  # best-effort mirror into the Story Graph
    rag_index.sync_setting(setting)  # best-effort embed into the vector store
    return setting


def update_setting(db: Session, setting_id: str, data: SettingUpdate) -> Setting:
    setting = get_setting(db, setting_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    graph_writer.sync_setting(db, setting)  # best-effort mirror into the Story Graph
    rag_index.sync_setting(setting)  # best-effort re-embed
    return setting


def delete_setting(db: Session, setting_id: str) -> None:
    # Scenarios keep their (now dangling) setting_id — the frontend falls back.
    db.delete(get_setting(db, setting_id))
    _purge_entity_context_docs(db, "setting", setting_id)  # drop attached docs + embeddings
    db.commit()
    graph_writer.remove_node(setting_id)  # best-effort removal from the Story Graph
    rag_index.remove("setting", setting_id)  # best-effort drop from the vector store


# ---- scenarios -------------------------------------------------------------


def list_scenarios(db: Session, storyline_id: str) -> list[Scenario]:
    get_storyline(db, storyline_id)
    return list(
        db.scalars(
            select(Scenario)
            .where(Scenario.storyline_id == storyline_id)
            .order_by(Scenario.position, Scenario.title)
        )
    )


def get_scenario(db: Session, scenario_id: str) -> Scenario:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise APIError(404, "not_found", f"Scenario '{scenario_id}' not found.")
    return scenario


def create_scenario(db: Session, storyline_id: str, data: ScenarioCreate) -> Scenario:
    get_storyline(db, storyline_id)
    _require_unique_id(db, Scenario, data.id)
    _validate_refs(db, storyline_id, data.cast_ids, data.setting_id)
    scenario = Scenario(
        id=data.id or _gen_hex_id(db, Scenario, 4),
        storyline_id=storyline_id,
        title=data.title,
        genre=data.genre,
        tone=data.tone,
        goal=data.goal,
        setting_id=data.setting_id,
        opening=data.opening,
        cast_ids=list(data.cast_ids),
        branches=[b.model_dump() for b in data.branches],
        max_turns=data.max_turns,
        suggestions_count=data.suggestions_count,
        position=_next_position(db, Scenario, storyline_id),
        image=data.image,
        scene_art_positive=data.scene_art_positive,
        scene_art_negative=data.scene_art_negative,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    rag_index.sync_scenario(scenario)  # best-effort embed into the vector store
    return scenario


def update_scenario(db: Session, scenario_id: str, data: ScenarioUpdate) -> Scenario:
    scenario = get_scenario(db, scenario_id)
    patch = data.model_dump(exclude_unset=True)
    if "cast_ids" in patch or "setting_id" in patch:
        _validate_refs(
            db,
            scenario.storyline_id,
            patch.get("cast_ids", scenario.cast_ids),
            patch.get("setting_id", scenario.setting_id),
        )
    for key, value in patch.items():
        setattr(scenario, key, value)
    db.commit()
    db.refresh(scenario)
    rag_index.sync_scenario(scenario)  # best-effort re-embed
    return scenario


def delete_scenario(db: Session, scenario_id: str) -> None:
    db.delete(get_scenario(db, scenario_id))
    _purge_entity_context_docs(db, "scenario", scenario_id)  # drop attached docs + embeddings
    db.commit()
    rag_index.remove("scenario", scenario_id)  # best-effort drop from the vector store
