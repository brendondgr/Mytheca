"""The export carries what the player ASKED for, not only what the scene did.

A directed turn raises exactly one question for anyone reading the record afterwards — did
it deliver? — and an export that shows only the beats cannot answer it. The direction is on
the `user_turn` row; these assert both renderings surface it.
"""

from __future__ import annotations

from app.models import Event
from app.services import events_store, session_export


def _world(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _turn(db, scid, session_id, seq, **data):
    db.add(
        Event(
            type="user_turn", seq=seq, scenario_id=scid, session_id=session_id,
            visibility="public", data=data,
        )
    )
    db.commit()


def test_the_json_export_carries_the_direction(client, storyline_id, db_session):
    _cid, scid = _world(client, storyline_id)
    s = events_store.create_session(db_session, scid)
    _turn(
        db_session, scid, s.id, 0,
        text="I hold my ground.", directedAt=None, pov=None,
        guidance="Mei should lose her temper.", taggedDocIds=[],
    )

    turns = session_export.group_turns(
        events_store.session_events(db_session, s.id), [], {}
    )
    assert turns[0]["player"]["guidance"] == "Mei should lose her temper."


def test_the_markdown_export_renders_the_direction_under_the_line(client, storyline_id, db_session):
    _cid, scid = _world(client, storyline_id)
    s = events_store.create_session(db_session, scid)
    _turn(
        db_session, scid, s.id, 0,
        text="I hold my ground.", directedAt=None, pov=None,
        guidance="Mei should lose her temper.", taggedDocIds=[],
    )

    md = client.get(f"/api/play/{scid}/sessions/{s.id}/export?format=md").text
    assert "I hold my ground." in md
    assert "_Direction:_ Mei should lose her temper." in md


def test_an_undirected_turn_renders_no_direction_line(client, storyline_id, db_session):
    _cid, scid = _world(client, storyline_id)
    s = events_store.create_session(db_session, scid)
    _turn(db_session, scid, s.id, 0, text="Just a line.", directedAt=None, pov=None)

    md = client.get(f"/api/play/{scid}/sessions/{s.id}/export?format=md").text
    assert "_Direction:_" not in md


def test_a_text_less_turn_reads_as_letting_the_scene_run(client, storyline_id, db_session):
    """A Continue turn used to render as an empty **You**: line."""
    _cid, scid = _world(client, storyline_id)
    s = events_store.create_session(db_session, scid)
    _turn(db_session, scid, s.id, 0, text="", directedAt=None, pov=None, continuation=True)

    md = client.get(f"/api/play/{scid}/sessions/{s.id}/export?format=md").text
    assert "_(let the scene continue)_" in md


def test_a_row_written_before_direction_was_persisted_still_exports(client, storyline_id, db_session):
    """Legacy rows carry neither key; the export must read them with a default, not crash."""
    _cid, scid = _world(client, storyline_id)
    s = events_store.create_session(db_session, scid)
    _turn(db_session, scid, s.id, 0, text="An old line.", directedAt=None)

    turns = session_export.group_turns(events_store.session_events(db_session, s.id), [], {})
    assert turns[0]["player"]["guidance"] == ""
    assert turns[0]["player"]["taggedDocIds"] == []


def test_the_direction_and_files_trace_steps_are_labelled(client, storyline_id):
    """Both were emitted but unlabelled, so they rendered under a raw step name."""
    assert session_export._STEP_LABELS["direction"] == "Scene direction"
    assert session_export._STEP_LABELS["files"] == "Tagged files"
