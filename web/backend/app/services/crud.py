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
from app.models import Character, Scenario, Setting, Storyline
from app.services import graph_writer
from app.schemas.character import CharacterCreate, CharacterUpdate
from app.schemas.scenario import ScenarioCreate, ScenarioUpdate
from app.schemas.setting import SettingCreate, SettingUpdate
from app.schemas.storyline import StorylineCreate, StorylineUpdate

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


def list_storylines(db: Session) -> list[Storyline]:
    return list(db.scalars(select(Storyline).order_by(Storyline.position, Storyline.title)))


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
    return sl


def update_storyline(db: Session, storyline_id: str, data: StorylineUpdate) -> Storyline:
    sl = get_storyline(db, storyline_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sl, key, value)
    db.commit()
    db.refresh(sl)
    return sl


def delete_storyline(db: Session, storyline_id: str) -> None:
    db.delete(get_storyline(db, storyline_id))  # ORM cascade removes children
    db.commit()


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
        position=_next_position(db, Character, storyline_id),
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    graph_writer.sync_character(db, char)  # best-effort mirror into the Story Graph
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
    return char


def delete_character(db: Session, character_id: str) -> None:
    char = get_character(db, character_id)
    storyline_id = char.storyline_id
    db.delete(char)
    # Mirror the frontend: drop the id from every scenario's cast in this storyline.
    for scenario in db.scalars(select(Scenario).where(Scenario.storyline_id == storyline_id)):
        if character_id in (scenario.cast_ids or []):
            scenario.cast_ids = [cid for cid in scenario.cast_ids if cid != character_id]
    db.commit()
    graph_writer.remove_node(character_id)  # best-effort removal from the Story Graph


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
        # Timeline is play-accrued (§4.1) — store an empty log at authoring, never None.
        timeline=[e.model_dump() for e in (data.timeline or [])],
        position=_next_position(db, Setting, storyline_id),
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    graph_writer.sync_setting(db, setting)  # best-effort mirror into the Story Graph
    return setting


def update_setting(db: Session, setting_id: str, data: SettingUpdate) -> Setting:
    setting = get_setting(db, setting_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    graph_writer.sync_setting(db, setting)  # best-effort mirror into the Story Graph
    return setting


def delete_setting(db: Session, setting_id: str) -> None:
    # Scenarios keep their (now dangling) setting_id — the frontend falls back.
    db.delete(get_setting(db, setting_id))
    db.commit()
    graph_writer.remove_node(setting_id)  # best-effort removal from the Story Graph


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
        position=_next_position(db, Scenario, storyline_id),
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
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
    return scenario


def delete_scenario(db: Session, scenario_id: str) -> None:
    db.delete(get_scenario(db, scenario_id))
    db.commit()
