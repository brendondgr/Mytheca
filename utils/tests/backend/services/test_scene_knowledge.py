"""What the scene knows — assembled from the latest turn's persisted trace rows."""

from __future__ import annotations

from app.models import PlaySession, Scenario, Storyline, TurnTrace
from app.services import scene_knowledge


def _scene(db):
    db.add(Storyline(id="w1", title="W1"))
    db.add(Scenario(id="sc1", title="Plot", storyline_id="w1", cast_ids=["c1", "c2"]))
    session = PlaySession(id="ps1", scenario_id="sc1")
    db.add(session)
    db.commit()
    return session


def _trace(db, *, turn=1, n=0, step="relationship", detail="", data=None):
    db.add(
        TurnTrace(
            session_id="ps1",
            scenario_id="sc1",
            turn=turn,
            n=n,
            step=step,
            detail=detail,
            data=data or {},
        )
    )


def test_a_speaker_who_takes_several_beats_is_listed_once(db_session):
    """A live panel showed one character's ties repeated verbatim three times in eight."""
    session = _scene(db_session)
    note = "Maerin Voss suspects you. You knows Wren Calloway."
    for n in range(3):
        _trace(db_session, n=n, detail=note, data={"characterId": "c1"})
    db_session.add(
        TurnTrace(
            session_id="ps1",
            scenario_id="sc1",
            turn=1,
            n=9,
            step="assemble",
            data={"cast": [{"id": "c1", "name": "Doran"}]},
        )
    )
    db_session.commit()

    out = scene_knowledge.scene_knowledge(db_session, session)

    assert len(out.relationships) == 1
    assert out.relationships[0].endswith(note)


def test_a_note_that_changed_mid_turn_still_shows_twice(db_session):
    """Collapsing those would answer a different question than the panel asks."""
    session = _scene(db_session)
    _trace(db_session, n=0, detail="You trusts Wren Calloway.", data={"characterId": "c1"})
    _trace(db_session, n=1, detail="You suspects Wren Calloway.", data={"characterId": "c1"})
    db_session.commit()

    out = scene_knowledge.scene_knowledge(db_session, session)

    assert len(out.relationships) == 2


def test_only_the_latest_turn_is_reported(db_session):
    session = _scene(db_session)
    _trace(db_session, turn=1, detail="An older tie.", data={"characterId": "c1"})
    _trace(db_session, turn=2, detail="The current tie.", data={"characterId": "c1"})
    db_session.commit()

    out = scene_knowledge.scene_knowledge(db_session, session)

    assert [r for r in out.relationships if "older" in r] == []
    assert any("current" in r for r in out.relationships)


def test_a_row_with_no_detail_is_not_a_line(db_session):
    session = _scene(db_session)
    _trace(db_session, detail="", data={"characterId": "c1"})
    db_session.commit()

    assert scene_knowledge.scene_knowledge(db_session, session).relationships == []
