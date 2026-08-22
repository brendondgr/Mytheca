"""Turn-loop event/session store: seq, session resolution, persistence, unique seq."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import APIError
from app.events.stream import TurnTraceFrame, build_event
from app.models import Event, PlaySession, Scenario, Storyline, TurnTrace
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
    # `pov` defaults to None (today's guide/narrator behavior) alongside the existing keys.
    # `guidance`/`taggedDocIds` are written on every row so a rewind or turn-scope re-roll can
    # replay the turn with what it rode in with; both are empty for an undirected, untagged turn.
    assert stored.data == {
        "text": "hi",
        "directedAt": "mei",
        "pov": None,
        "guidance": None,
        "taggedDocIds": [],
    }


def test_record_user_turn_persists_pov(db_session):
    # Player POV: the character id the line was spoken AS is carried on the row so reload
    # can reproduce it as that character's beat rather than a left-side player beat.
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    event = events_store.record_user_turn(
        db_session, scenario_id=scenario.id, session_id=session.id, seq=0,
        text="I have nothing to say to you.", directed_at=None, pov="mei",
    )
    stored = db_session.get(Event, event.id)
    assert stored.data == {
        "text": "I have nothing to say to you.",
        "directedAt": None,
        "pov": "mei",
        "guidance": None,
        "taggedDocIds": [],
    }


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


def test_persist_trace_stores_step_ordered_by_turn_and_n(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    events_store.persist_trace(
        db_session,
        session_id=session.id,
        scenario_id=scenario.id,
        turn=0,
        frame=TurnTraceFrame(n=2, step="lore", title="RAG look-up", detail="matched", data={"fetched": True}),
    )
    rows = db_session.query(TurnTrace).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.turn, row.n, row.step) == (0, 2, "lore")
    assert row.data == {"fetched": True}  # graph/RAG payload round-trips


def test_touch_session_bumps_updated_at(db_session):
    scenario = _world(db_session)
    session = events_store.create_session(db_session, scenario.id)
    original = session.updated_at
    session.updated_at = original.replace(year=2000)
    db_session.commit()
    events_store.touch_session(db_session, session.id)
    refreshed = db_session.get(PlaySession, session.id)
    assert refreshed.updated_at.year != 2000
