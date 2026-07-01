"""Turn-loop event/session store: seq, session resolution, persistence, unique seq."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import APIError
from app.events.stream import build_event
from app.models import Event, PlaySession, Scenario, Storyline
from app.services import events_store


def _world(db) -> Scenario:
    db.add(Storyline(id="embergate", title="Embergate"))
    db.commit()
    scenario = Scenario(storyline_id="embergate", title="Standoff")
    db.add(scenario)
    db.commit()
    return scenario


def test_next_seq_starts_at_zero_then_increments(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    assert events_store.next_seq(db_session, session.id) == 0
    db_session.add(Event(type="narration", seq=0, scenario_id=scenario.id, session_id=session.id, data={}))
    db_session.commit()
    assert events_store.next_seq(db_session, session.id) == 1


def test_resolve_session_creates_when_absent(db_session):
    scenario = _world(db_session)
    session = events_store.resolve_session(db_session, scenario.id, None)
    assert isinstance(session, PlaySession) and session.scenario_id == scenario.id


def test_resolve_session_returns_existing(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    assert events_store.resolve_session(db_session, scenario.id, session.id).id == session.id


def test_resolve_session_unknown_raises_404(db_session):
    scenario = _world(db_session)
    with pytest.raises(APIError) as exc:
        events_store.resolve_session(db_session, scenario.id, "ps_missing")
    assert exc.value.status_code == 404


def test_resolve_session_wrong_scenario_raises_400(db_session):
    scenario = _world(db_session)
    other = Scenario(storyline_id="embergate", title="Other")
    db_session.add(other)
    db_session.commit()
    session = events_store.create_session(db_session, other.id)
    with pytest.raises(APIError) as exc:
        events_store.resolve_session(db_session, scenario.id, session.id)
    assert exc.value.status_code == 400


def test_record_user_turn_persists_text(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    event = events_store.record_user_turn(
        db_session, scenario_id=scenario.id, session_id=session.id, seq=0, text="hi", directed_at="mei"
    )
    stored = db_session.get(Event, event.id)
    assert stored.type == "user_turn"
    assert stored.data == {"text": "hi", "directedAt": "mei"}


def test_persist_story_event_preserves_id_and_camel_data(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    event = build_event(
        "character_dialogue",
        {"characterId": "maerin", "text": "Hi", "done": True},
        scenario_id=scenario.id,
        session_id=session.id,
        seq=0,
        event_id="ev_fixed",
    )
    row = events_store.persist_story_event(db_session, event)
    assert row.id == "ev_fixed"
    stored = db_session.get(Event, "ev_fixed")
    assert stored.type == "character_dialogue"
    assert stored.data["characterId"] == "maerin"  # camelCase wire shape persisted


def test_session_seq_unique_constraint(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    db_session.add(Event(type="narration", seq=0, scenario_id=scenario.id, session_id=session.id, data={}))
    db_session.commit()
    db_session.add(Event(type="character_action", seq=0, scenario_id=scenario.id, session_id=session.id, data={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
