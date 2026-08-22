"""``events_store`` play-through record helpers: create with lineage, rename, delete.

The API-level behaviour lives in ``utils/tests/backend/api/test_play_sessions_crud.py``;
this covers the store functions directly, including the lineage fields that later phases
(branch, rewind) set and that no endpoint writes yet.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.models import Event
from app.services import events_store


@pytest.fixture
def scenario_id(client, storyline_id) -> str:
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]


def test_create_session_defaults_have_no_name_or_lineage(db_session, scenario_id):
    session = events_store.create_session(db_session, scenario_id)
    assert session.name is None
    assert session.parent_session_id is None
    assert session.fork_seq is None


def test_create_session_records_lineage(db_session, scenario_id):
    """Branch and rewind both set these together; nothing writes them yet, so this is the
    contract those phases build against."""
    parent = events_store.create_session(db_session, scenario_id)
    fork = events_store.create_session(
        db_session,
        scenario_id,
        name="Before rewind",
        parent_session_id=parent.id,
        fork_seq=7,
    )
    assert fork.name == "Before rewind"
    assert fork.parent_session_id == parent.id
    assert fork.fork_seq == 7


def test_create_session_treats_a_blank_name_as_unnamed(db_session, scenario_id):
    session = events_store.create_session(db_session, scenario_id, name="   ")
    assert session.name is None


def test_rename_session_trims_and_clears(db_session, scenario_id):
    session = events_store.create_session(db_session, scenario_id)
    assert events_store.rename_session(db_session, session.id, "  Kind run ").name == "Kind run"
    assert events_store.rename_session(db_session, session.id, "").name is None


def test_rename_session_bumps_recency(db_session, scenario_id):
    """The tray sorts on ``updated_at``; a rename is a visible act and should surface the row."""
    older = events_store.create_session(db_session, scenario_id)
    events_store.create_session(db_session, scenario_id)
    events_store.rename_session(db_session, older.id, "Now most recent")
    assert events_store.list_sessions(db_session, scenario_id)[0].id == older.id


def test_rename_unknown_session_raises(db_session):
    with pytest.raises(APIError):
        events_store.rename_session(db_session, "ps_nope", "x")


def test_delete_session_cascades_its_events(db_session, scenario_id):
    session = events_store.create_session(db_session, scenario_id)
    events_store.record_user_turn(
        db_session,
        scenario_id=scenario_id,
        session_id=session.id,
        seq=0,
        text="A line.",
        directed_at=None,
    )
    assert db_session.query(Event).filter(Event.session_id == session.id).count() == 1

    events_store.delete_session(db_session, session.id)

    assert db_session.query(Event).filter(Event.session_id == session.id).count() == 0
    assert events_store.list_sessions(db_session, scenario_id) == []


def test_delete_parent_orphans_the_fork_rather_than_removing_it(db_session, scenario_id):
    """``parent_session_id`` is ``ondelete="SET NULL"`` on purpose: deleting the play-through
    you branched *from* must not take the branch with it."""
    parent = events_store.create_session(db_session, scenario_id)
    fork = events_store.create_session(
        db_session, scenario_id, parent_session_id=parent.id, fork_seq=3
    )

    events_store.delete_session(db_session, parent.id)

    surviving = events_store.list_sessions(db_session, scenario_id)
    assert [s.id for s in surviving] == [fork.id]


def test_delete_unknown_session_raises(db_session):
    with pytest.raises(APIError):
        events_store.delete_session(db_session, "ps_nope")


def test_record_user_turn_persists_guidance_and_tagged_docs(db_session, scenario_id):
    session = events_store.create_session(db_session, scenario_id)
    row = events_store.record_user_turn(
        db_session,
        scenario_id=scenario_id,
        session_id=session.id,
        seq=0,
        text="I hold my ground.",
        directed_at=None,
        pov="ch_mei",
        guidance="  Mei should snap.  ",
        tagged_doc_ids=["cd_1", "cd_2"],
    )
    assert row.data["guidance"] == "Mei should snap."
    assert row.data["taggedDocIds"] == ["cd_1", "cd_2"]
    assert row.data["pov"] == "ch_mei"


def test_record_user_turn_without_direction_stores_none_not_empty_string(db_session, scenario_id):
    """``None`` and ``""`` read differently downstream — the composer restores one and not
    the other — so a turn with no direction must not persist a falsy string."""
    session = events_store.create_session(db_session, scenario_id)
    row = events_store.record_user_turn(
        db_session,
        scenario_id=scenario_id,
        session_id=session.id,
        seq=0,
        text="Just a line.",
        directed_at=None,
    )
    assert row.data["guidance"] is None
    assert row.data["taggedDocIds"] == []


def test_session_summary_carries_the_lineage_fields(db_session, scenario_id):
    parent = events_store.create_session(db_session, scenario_id)
    fork = events_store.create_session(
        db_session, scenario_id, name="Fork", parent_session_id=parent.id, fork_seq=2
    )
    summary = events_store.session_summary(db_session, fork)
    assert summary.name == "Fork"
    assert summary.parent_session_id == parent.id
    assert summary.fork_seq == 2
