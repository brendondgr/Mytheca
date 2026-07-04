"""Scene presence — event-log fold + selectability + the deterministic vital trigger."""

from __future__ import annotations

from app.models import Character, Event, Scenario, Storyline
from app.models.stat import StatDefinition
from app.services import events_store, presence


def _session(db) -> str:
    db.add(Storyline(id="embergate", title="Embergate", genre="Maritime"))
    db.commit()
    db.add(Character(id="c_mei", storyline_id="embergate", name="Mei"))
    sc = Scenario(storyline_id="embergate", title="Standoff", cast_ids=["c_mei"])
    db.add(sc)
    db.commit()
    return events_store.create_session(db, sc.id).id, sc.id


def _status(db, *, session_id: str, scenario_id: str, seq: int, cid: str, status: str) -> None:
    db.add(
        Event(
            type="character_status_change",
            seq=seq,
            scenario_id=scenario_id,
            session_id=session_id,
            data={"characterId": cid, "status": status, "reason": "", "auto": True},
        )
    )
    db.commit()


def test_no_events_defaults_present(db_session):
    session_id, _ = _session(db_session)
    assert presence.current_presence(db_session, session_id) == {}
    assert presence.status_for({}, "c_mei") == "present"


def test_fold_latest_wins(db_session):
    session_id, scenario_id = _session(db_session)
    _status(db_session, session_id=session_id, scenario_id=scenario_id, seq=1, cid="c_mei", status="unconscious")
    _status(db_session, session_id=session_id, scenario_id=scenario_id, seq=2, cid="c_mei", status="present")
    _status(db_session, session_id=session_id, scenario_id=scenario_id, seq=3, cid="c_mei", status="dead")
    presence_map = presence.current_presence(db_session, session_id)
    assert presence_map["c_mei"] == "dead"  # latest by seq wins


def test_fold_is_per_session(db_session):
    session_id, scenario_id = _session(db_session)
    other = events_store.create_session(db_session, scenario_id).id
    _status(db_session, session_id=other, scenario_id=scenario_id, seq=1, cid="c_mei", status="dead")
    # The queried session has no status events → empty map (not the other session's).
    assert presence.current_presence(db_session, session_id) == {}


def test_selectable_and_terminal():
    assert presence.is_selectable("present")
    assert not any(presence.is_selectable(s) for s in ("unconscious", "departed", "left", "dead"))
    assert presence.is_terminal("dead")
    assert not presence.is_terminal("departed")


def test_normalize_status():
    assert presence.normalize_status(" Dead ") == "dead"
    assert presence.normalize_status("PRESENT") == "present"
    assert presence.normalize_status("vaporized") is None
    assert presence.normalize_status(None) is None


def test_vital_status_for_health_floor():
    health = StatDefinition(storyline_id="embergate", key="health", display_name="Health", min=0, max=100, default=100)
    trust = StatDefinition(storyline_id="embergate", key="trust", display_name="Trust", min=0, max=100, default=50)
    assert presence.vital_status_for(health, 0) == "unconscious"
    assert presence.vital_status_for(health, -5) == "unconscious"  # already clamped, defensive
    assert presence.vital_status_for(health, 20) is None  # still standing
    assert presence.vital_status_for(trust, 0) is None  # only the vital stat triggers
