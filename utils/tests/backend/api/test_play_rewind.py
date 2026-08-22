"""Rewind to here — cut a play-through back to a beat and continue from it.

The owner's framing: "something happens you don't want... the conversation continues with a
natural prompt given to the user, the user says what they want to happen and that continues
the conversation forward from that point."

So the cut is only half of it. The other half is that the player's own line comes BACK,
editable, with the direction and attachments it rode in with.
"""

from __future__ import annotations

import httpx

from app.services import llm, session_stats

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Hold.</thinking>\n"
    "Mei does not move.\n"
    '"Not tonight."'
)


def _patch_llm(monkeypatch, content: str = _EMISSION):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scenario(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _turn(client, scid, text, session_id=None, **extra):
    body = {"text": text, **extra}
    if session_id:
        body["sessionId"] = session_id
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass


def _history(client, scid, sid):
    return client.get(f"/api/play/{scid}/sessions/{sid}").json()


def _played(client, storyline_id, monkeypatch, turns=3):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    _turn(client, scid, "Turn one.")
    sid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    for i in range(2, turns + 1):
        _turn(client, scid, f"Turn {i}.", session_id=sid)
    return cid, scid, sid


def _turn_rows(client, scid, sid):
    return [e for e in _history(client, scid, sid)["events"] if e["type"] == "user_turn"]


def test_rewind_removes_the_containing_turn_and_everything_after(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=3)
    turns = _turn_rows(client, scid, sid)
    assert [t["data"]["text"] for t in turns] == ["Turn one.", "Turn 2.", "Turn 3."]

    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]}
    )
    assert resp.status_code == 200
    body = resp.json()

    remaining = [t["data"]["text"] for t in _turn_rows(client, scid, sid)]
    assert remaining == ["Turn one."]
    assert body["removedEvents"] > 0


def test_rewind_hands_the_players_line_back(client, storyline_id, monkeypatch):
    """The 'natural prompt' the owner asked for."""
    cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=1)
    _turn(
        client, scid, "I say the wrong thing.", session_id=sid,
        povCharacterId=cid, guidance="Mei should storm out.",
    )
    turns = _turn_rows(client, scid, sid)

    body = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[-1]["id"]}
    ).json()

    restored = body["restoredTurn"]
    assert restored["text"] == "I say the wrong thing."
    assert restored["guidance"] == "Mei should storm out."
    assert restored["pov"] == cid


def test_rewind_deletes_the_opening_row_so_the_line_is_not_doubled(client, storyline_id, monkeypatch):
    """The player is about to rewrite that line; leaving the row would duplicate it."""
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]})

    texts = [t["data"]["text"] for t in _turn_rows(client, scid, sid)]
    assert "Turn 2." not in texts


def test_rewind_keeps_a_snapshot_play_through_by_default(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=3)
    turns = _turn_rows(client, scid, sid)

    body = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]}
    ).json()

    snap_id = body["snapshotSessionId"]
    assert snap_id
    snap_turns = [t["data"]["text"] for t in _turn_rows(client, scid, snap_id)]
    assert snap_turns == ["Turn one.", "Turn 2.", "Turn 3."]  # the whole pre-cut history

    listed = {s["id"]: s for s in client.get(f"/api/play/{scid}/sessions").json()["sessions"]}
    assert listed[snap_id]["name"].startswith("Before rewind")
    assert listed[snap_id]["parentSessionId"] == sid


def test_rewind_without_a_snapshot_leaves_no_extra_play_through(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)
    before = len(client.get(f"/api/play/{scid}/sessions").json()["sessions"])

    body = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind",
        json={"atEventId": turns[1]["id"], "keepSnapshot": False},
    ).json()

    assert body["snapshotSessionId"] is None
    after = len(client.get(f"/api/play/{scid}/sessions").json()["sessions"])
    assert after == before


def test_rewind_rolls_the_stats_back(client, storyline_id, monkeypatch, db_session):
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "suspicion", "displayName": "Suspicion", "min": 0, "max": 100, "default": 50},
    )
    cid, scid = _scenario(client, storyline_id)
    _patch_llm(monkeypatch, _EMISSION + '\n<type:state_update>\n{"key":"suspicion","delta":10}')
    _turn(client, scid, "Turn one.")
    sid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    _turn(client, scid, "Turn two.", session_id=sid)

    after_two = session_stats.resolve(db_session, sid, cid)["suspicion"]
    turns = _turn_rows(client, scid, sid)

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]})

    rolled_back = session_stats.resolve(db_session, sid, cid)["suspicion"]
    assert rolled_back < after_two


def test_rewind_prunes_the_traces_of_the_cut_turns(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=3)
    turns = _turn_rows(client, scid, sid)
    cut_at = turns[1]["seq"]

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]})

    traces = _history(client, scid, sid)["traces"]
    assert all(t["turn"] < cut_at for t in traces)


def test_rewind_409s_on_a_stale_expected_seq(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)
    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind",
        json={"atEventId": turns[0]["id"], "expectedSeq": 0},
    )
    assert resp.status_code == 409
    # ...and nothing was cut.
    assert len(_turn_rows(client, scid, sid)) == 2


def test_the_scene_continues_after_a_rewind(client, storyline_id, monkeypatch):
    """The point of the whole feature: play carries on in the same play-through."""
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]})
    _turn(client, scid, "Something else happens instead.", session_id=sid)

    texts = [t["data"]["text"] for t in _turn_rows(client, scid, sid)]
    assert texts == ["Turn one.", "Something else happens instead."]


def test_rewind_to_the_first_turn_empties_the_play_through(client, storyline_id, monkeypatch):
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[0]["id"]})

    assert _history(client, scid, sid)["events"] == []


def test_rewind_succeeds_without_redis_neo4j_or_qdrant(client, storyline_id, monkeypatch):
    """The suite runs with none of them; if any were required this raises rather than skips."""
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)
    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]}
    )
    assert resp.status_code == 200


def test_rewind_cancels_the_direction_the_cut_turns_raised(
    client, storyline_id, monkeypatch, db_session
):
    """A direction outlives the turn it rode in on — deliberately, and it is most of why
    the scene stopped forgetting what the player asked for. But a debt raised by a turn the
    player has just deleted is owed to a turn that no longer exists, and leaving it makes
    the scene chase something un-asked-for in the very next beat after a rewind."""
    from app.models import PlaySession

    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)

    # One debt from the turn that survives, one from the turn about to be cut.
    row = db_session.get(PlaySession, sid)
    row.standing_direction = [
        {"id": "keep", "text": "Have Mei name the ledger.", "fromTurn": turns[0]["seq"]},
        {"id": "drop", "text": "Have the lamp go over.", "fromTurn": turns[1]["seq"]},
    ]
    db_session.add(row)
    db_session.commit()

    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]}
    )
    assert resp.status_code == 200

    db_session.expire_all()
    standing = db_session.get(PlaySession, sid).standing_direction or []
    assert [r["id"] for r in standing] == ["keep"]
    # And the history route reports it, so a resumed client cannot re-render a dead debt.
    assert [s["id"] for s in _history(client, scid, sid)["standingDirection"]] == ["keep"]


def test_rewind_clears_the_casts_interior_state(client, storyline_id, monkeypatch):
    """The Redis half of the same requirement: each character's disposition is derived from
    the beats the cut removed, and the assembler reads it straight into the next prompt.
    The suite has no Redis, so this asserts the call; `test_interior.py` covers its effect."""
    from app.services import session_state

    cleared: list[str] = []
    monkeypatch.setattr(
        session_state.interior, "clear_session", lambda s: cleared.append(s) or 0
    )
    _cid, scid, sid = _played(client, storyline_id, monkeypatch, turns=2)
    turns = _turn_rows(client, scid, sid)

    client.post(f"/api/play/{scid}/sessions/{sid}/rewind", json={"atEventId": turns[1]["id"]})

    assert sid in cleared
