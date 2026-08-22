"""History-mutation primitives — the shared floor under rewind, branch, edit and re-roll.

The point of testing these once, here, is that four endpoints will share them. If each
re-implemented truncation the drift would be silent: a stale Redis buffer feeds the model a
beat the player deleted, and it reads as the model ignoring them.

The whole suite runs with **no** Redis, Neo4j or Qdrant, which is also how this proves the
"never let a missing service break the operation" requirement.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.models import Event, TurnTrace
from app.services import events_store, session_state, session_stats, stats


@pytest.fixture
def world(client, storyline_id):
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "trust", "displayName": "Trust", "min": 0, "max": 100, "default": 50},
    )
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return {"character_id": cid, "scenario_id": scid, "storyline_id": storyline_id}


def _event(db, session, scenario_id, seq, type_, data, visibility="public"):
    row = Event(
        type=type_, seq=seq, scenario_id=scenario_id, session_id=session.id,
        visibility=visibility, data=data,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def played(db_session, world):
    """Two turns: a player line + a beat each, with a stat change in each turn."""
    s = events_store.create_session(db_session, world["scenario_id"])
    cid = world["character_id"]
    scid = world["scenario_id"]
    rows = {
        "t1_user": _event(db_session, s, scid, 0, "user_turn", {"text": "First line.", "pov": None}),
        "t1_beat": _event(db_session, s, scid, 1, "character_prose", {"characterId": cid, "text": "Beat one.", "done": True}),
        "t1_stat": _event(db_session, s, scid, 2, "state_update", {"stat": {"characterId": cid, "key": "trust", "value": 60, "delta": 10}}),
        "t2_user": _event(db_session, s, scid, 3, "user_turn", {"text": "Second line.", "pov": None}),
        "t2_beat": _event(db_session, s, scid, 4, "character_prose", {"characterId": cid, "text": "Beat two.", "done": True}),
        "t2_stat": _event(db_session, s, scid, 5, "state_update", {"stat": {"characterId": cid, "key": "trust", "value": 20, "delta": -40}}),
    }
    for turn in (0, 3):
        db_session.add(TurnTrace(session_id=s.id, scenario_id=scid, turn=turn, n=1, step="turn", title="You", detail="", data={}))
    db_session.commit()
    session_stats.apply(db_session, s.id, cid, {"trust": 20})
    return {"session": s, "rows": rows, **world}


# ---- preconditions --------------------------------------------------------


def test_latest_seq_of_an_empty_session_is_minus_one(db_session, world):
    s = events_store.create_session(db_session, world["scenario_id"])
    assert session_state.latest_seq(db_session, s.id) == -1


def test_require_expected_seq_passes_on_a_current_view(db_session, played):
    session_state.require_expected_seq(db_session, played["session"].id, 5)


def test_require_expected_seq_409s_on_a_stale_view(db_session, played):
    with pytest.raises(APIError) as exc:
        session_state.require_expected_seq(db_session, played["session"].id, 3)
    assert exc.value.status_code == 409


def test_require_expected_seq_skips_when_the_caller_does_not_care(db_session, played):
    session_state.require_expected_seq(db_session, played["session"].id, None)


# ---- turn boundary --------------------------------------------------------


def test_turn_boundary_resolves_a_beat_to_the_turn_that_opened_it(db_session, played):
    opening = session_state.turn_boundary(db_session, played["session"].id, played["rows"]["t2_beat"].id)
    assert opening.seq == 3
    assert opening.data["text"] == "Second line."


def test_turn_boundary_on_the_opening_row_is_itself(db_session, played):
    opening = session_state.turn_boundary(db_session, played["session"].id, played["rows"]["t1_user"].id)
    assert opening.seq == 0


def test_turn_boundary_rejects_an_event_from_another_session(db_session, played, world):
    other = events_store.create_session(db_session, world["scenario_id"])
    with pytest.raises(APIError) as exc:
        session_state.turn_boundary(db_session, other.id, played["rows"]["t1_beat"].id)
    assert exc.value.status_code == 404


# ---- truncation -----------------------------------------------------------


def test_truncate_removes_the_right_rows_and_no_others(db_session, played):
    s = played["session"]
    result = session_state.truncate_session(db_session, s.id, after_seq=2)

    assert result.removed_events == 3          # seq 3,4,5
    assert result.removed_turn_seqs == [3]
    surviving = [e.seq for e in events_store.session_events(db_session, s.id)]
    assert surviving == [0, 1, 2]


def test_truncate_prunes_the_traces_of_the_cut_turns_only(db_session, played):
    s = played["session"]
    result = session_state.truncate_session(db_session, s.id, after_seq=2)
    assert result.removed_traces == 1
    remaining = [t.turn for t in events_store.session_traces(db_session, s.id)]
    assert remaining == [0]


def test_truncate_replays_stats_to_the_surviving_events(db_session, played):
    """The second turn dropped trust to 20; cutting it must put it back to the 60 the first
    turn left, NOT to the baseline and NOT to the value that no longer happened."""
    s, cid = played["session"], played["character_id"]
    assert session_stats.resolve(db_session, s.id, cid)["trust"] == 20

    session_state.truncate_session(db_session, s.id, after_seq=2)

    assert session_stats.resolve(db_session, s.id, cid)["trust"] == 60


def test_truncating_every_stat_event_returns_to_the_authored_baseline(db_session, played):
    s, cid = played["session"], played["character_id"]
    stats.set_character_stats(db_session, cid, {"trust": 42})

    session_state.truncate_session(db_session, s.id, after_seq=1)

    assert session_stats.resolve(db_session, s.id, cid)["trust"] == 42


def test_truncate_to_nothing_empties_the_session(db_session, played):
    s = played["session"]
    result = session_state.truncate_session(db_session, s.id, after_seq=-1)
    assert result.removed_events == 6
    assert events_store.session_events(db_session, s.id) == []


def test_truncate_is_a_no_op_past_the_end(db_session, played):
    s = played["session"]
    result = session_state.truncate_session(db_session, s.id, after_seq=99)
    assert result.removed_events == 0
    assert len(events_store.session_events(db_session, s.id)) == 6


def test_truncate_runs_without_redis_or_neo4j(db_session, played):
    """The suite has neither. If either were required rather than best-effort, this raises."""
    result = session_state.truncate_session(db_session, played["session"].id, after_seq=2)
    assert result.cut_seq == 2


def test_rebuild_buffer_without_redis_offers_the_prose_rows_and_stores_nothing(db_session, played):
    """The suite has no Redis. The rebuild must still complete, and must count what it would
    have written: the two player lines and the two prose beats — never the `state_update`
    rows, and never an `internal_thought` (later speakers must not condition on another
    character's private deliberation)."""
    assert session_state.rebuild_buffer(db_session, played["session"].id) == 4


# ---- history copy ---------------------------------------------------------


def test_copy_history_produces_an_independent_session_with_identical_seqs(db_session, played, world):
    src = played["session"]
    dst = events_store.create_session(db_session, world["scenario_id"])

    copied = session_state.copy_history(db_session, src.id, dst.id, through_seq=2)

    assert copied == 3
    assert [e.seq for e in events_store.session_events(db_session, dst.id)] == [0, 1, 2]
    # The source is untouched — that is what makes a branch a branch.
    assert len(events_store.session_events(db_session, src.id)) == 6


def test_copied_events_are_new_rows_not_shared_ones(db_session, played, world):
    src = played["session"]
    dst = events_store.create_session(db_session, world["scenario_id"])
    session_state.copy_history(db_session, src.id, dst.id, through_seq=5)

    src_ids = {e.id for e in events_store.session_events(db_session, src.id)}
    dst_ids = {e.id for e in events_store.session_events(db_session, dst.id)}
    assert src_ids.isdisjoint(dst_ids)

    # Truncating the copy leaves the original whole.
    session_state.truncate_session(db_session, dst.id, after_seq=0)
    assert len(events_store.session_events(db_session, src.id)) == 6


def test_copy_history_carries_the_traces(db_session, played, world):
    src = played["session"]
    dst = events_store.create_session(db_session, world["scenario_id"])
    session_state.copy_history(db_session, src.id, dst.id, through_seq=5)
    assert [t.turn for t in events_store.session_traces(db_session, dst.id)] == [0, 3]


def test_copy_history_forks_the_stat_values(db_session, played, world):
    """A branch that started from the baseline while its copied transcript said otherwise
    would open contradicting its own history."""
    src, cid = played["session"], played["character_id"]
    dst = events_store.create_session(db_session, world["scenario_id"])

    session_state.copy_history(db_session, src.id, dst.id, through_seq=5)

    assert session_stats.resolve(db_session, dst.id, cid)["trust"] == 20
    session_stats.apply(db_session, dst.id, cid, {"trust": 1})
    assert session_stats.resolve(db_session, src.id, cid)["trust"] == 20
