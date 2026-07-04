"""Per-storyline / per-scenario ``prompt_overrides`` — persistence + schema coercion."""

from __future__ import annotations

from app.models import Scenario, Storyline
from app.schemas.scenario import ScenarioCreate, ScenarioRead, ScenarioUpdate
from app.schemas.storyline import StorylineCreate, StorylineRead, StorylineUpdate
from app.services import crud

_OVERRIDES = {"narrator.system": "Be terse and grim."}


def test_storyline_prompt_overrides_roundtrip_and_default(db_session):
    with_overrides = crud.create_storyline(
        db_session, StorylineCreate(id="grim", title="Grim", prompt_overrides=_OVERRIDES)
    )
    assert db_session.get(Storyline, "grim").prompt_overrides == _OVERRIDES

    # Omitted → defaults to {}, not NULL.
    plain = crud.create_storyline(db_session, StorylineCreate(id="plain", title="Plain"))
    assert plain.prompt_overrides == {}

    # Update replaces the map.
    crud.update_storyline(
        db_session, "grim", StorylineUpdate(prompt_overrides={"planner.system": "One beat only."})
    )
    assert db_session.get(Storyline, "grim").prompt_overrides == {"planner.system": "One beat only."}
    assert with_overrides.id == "grim"


def test_scenario_prompt_overrides_roundtrip_and_update(db_session):
    crud.create_storyline(db_session, StorylineCreate(id="w", title="W"))
    scn = crud.create_scenario(
        db_session, "w", ScenarioCreate(title="Scene", prompt_overrides=_OVERRIDES)
    )
    assert db_session.get(Scenario, scn.id).prompt_overrides == _OVERRIDES

    crud.update_scenario(
        db_session, scn.id, ScenarioUpdate(prompt_overrides={"director.branch": "Two options."})
    )
    assert db_session.get(Scenario, scn.id).prompt_overrides == {"director.branch": "Two options."}


def test_reads_coerce_null_overrides_to_empty_dict(db_session):
    """Older rows (NULL column) must serialize as {} through the *Read schemas."""
    crud.create_storyline(db_session, StorylineCreate(id="s", title="S"))
    scn = crud.create_scenario(db_session, "s", ScenarioCreate(title="Old"))
    # Simulate a pre-migration row where the column is NULL.
    db_session.get(Storyline, "s").prompt_overrides = None
    db_session.get(Scenario, scn.id).prompt_overrides = None
    db_session.commit()

    assert StorylineRead.model_validate(db_session.get(Storyline, "s")).prompt_overrides == {}
    assert ScenarioRead.model_validate(db_session.get(Scenario, scn.id)).prompt_overrides == {}


def test_scenario_read_serializes_overrides_camel(db_session):
    crud.create_storyline(db_session, StorylineCreate(id="c", title="C"))
    scn = crud.create_scenario(
        db_session, "c", ScenarioCreate(title="Scene", prompt_overrides=_OVERRIDES)
    )
    payload = ScenarioRead.model_validate(db_session.get(Scenario, scn.id)).model_dump(by_alias=True)
    assert payload["promptOverrides"] == _OVERRIDES
