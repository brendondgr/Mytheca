"""Branch from here — fork a play-through at a beat, leaving the original intact.

This is the non-destructive half of the machinery rewind uses. Proving the source is
untouched is the whole point: if a branch could disturb its parent, "try it a different way"
would cost you the story you already had.
"""

from __future__ import annotations

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Careful now.</thinking>\n"
    "Mei sets her cup down.\n"
    '"Say that again."'
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


def _turn(client, scid, text, session_id=None):
    body = {"text": text}
    if session_id:
        body["sessionId"] = session_id
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass


def _history(client, scid, sid):
    return client.get(f"/api/play/{scid}/sessions/{sid}").json()


def _played(client, storyline_id, monkeypatch, turns=2):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _cid, scid = _scenario(client, storyline_id)
    _turn(client, scid, "Turn one.")
    sid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    for i in range(2, turns + 1):
        _turn(client, scid, f"Turn {i}.", session_id=sid)
    return scid, sid


def test_branch_copies_through_the_chosen_turn_and_no_further(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch, turns=3)
    events = _history(client, scid, sid)["events"]
    first_turn = next(e for e in events if e["type"] == "user_turn")

    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch",
        json={"atEventId": first_turn["id"], "name": "The kinder road"},
    )
    assert resp.status_code == 201
    fork = resp.json()

    fork_events = _history(client, scid, fork["id"])["events"]
    # Exactly one player turn came across: the one the fork point is in.
    assert [e["data"]["text"] for e in fork_events if e["type"] == "user_turn"] == ["Turn one."]
    assert len(fork_events) < len(events)


def test_branch_leaves_the_parent_byte_identical(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch, turns=3)
    before = _history(client, scid, sid)["events"]
    first_turn = next(e for e in before if e["type"] == "user_turn")

    client.post(f"/api/play/{scid}/sessions/{sid}/branch", json={"atEventId": first_turn["id"]})

    after = _history(client, scid, sid)["events"]
    assert [(e["id"], e["seq"], e["type"]) for e in after] == [
        (e["id"], e["seq"], e["type"]) for e in before
    ]


def test_branch_records_its_lineage(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    first_turn = next(e for e in events if e["type"] == "user_turn")

    fork = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch", json={"atEventId": first_turn["id"]}
    ).json()

    assert fork["parentSessionId"] == sid
    assert fork["forkSeq"] is not None
    # And it shows up in the tray alongside its parent.
    listed = {s["id"]: s for s in client.get(f"/api/play/{scid}/sessions").json()["sessions"]}
    assert listed[fork["id"]]["parentSessionId"] == sid


def test_branch_gives_the_fork_new_event_rows(client, storyline_id, monkeypatch):
    """Copied, not shared — otherwise truncating the branch would gut its parent."""
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    fork = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch",
        json={"atEventId": events[-1]["id"]},
    ).json()

    fork_ids = {e["id"] for e in _history(client, scid, fork["id"])["events"]}
    assert fork_ids.isdisjoint({e["id"] for e in events})


def test_branch_preserves_seq_ordering(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    fork = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch", json={"atEventId": events[-1]["id"]}
    ).json()

    seqs = [e["seq"] for e in _history(client, scid, fork["id"])["events"]]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))  # UNIQUE (session_id, seq) still holds


def test_branch_can_be_continued_independently(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    fork = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch", json={"atEventId": events[-1]["id"]}
    ).json()

    _turn(client, scid, "Only in the branch.", session_id=fork["id"])

    fork_lines = [e["data"]["text"] for e in _history(client, scid, fork["id"])["events"] if e["type"] == "user_turn"]
    parent_lines = [e["data"]["text"] for e in _history(client, scid, sid)["events"] if e["type"] == "user_turn"]
    assert "Only in the branch." in fork_lines
    assert "Only in the branch." not in parent_lines


def test_branch_409s_on_a_stale_expected_seq(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch",
        json={"atEventId": events[0]["id"], "expectedSeq": 0},
    )
    assert resp.status_code == 409


def test_branch_accepts_a_current_expected_seq(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    events = _history(client, scid, sid)["events"]
    latest = max(e["seq"] for e in events)
    resp = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch",
        json={"atEventId": events[0]["id"], "expectedSeq": latest},
    )
    assert resp.status_code == 201


def test_branch_rejects_an_event_from_another_play_through(client, storyline_id, monkeypatch):
    scid, sid = _played(client, storyline_id, monkeypatch)
    other = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    events = _history(client, scid, sid)["events"]
    resp = client.post(
        f"/api/play/{scid}/sessions/{other}/branch", json={"atEventId": events[0]["id"]}
    )
    assert resp.status_code == 404


def test_branch_carries_what_the_parent_still_owed(client, storyline_id, monkeypatch, db_session):
    """A fork is the parent up to the fork point. The rolling summary is deliberately NOT
    copied (it would go stale the moment the branch diverged, with no seq to notice by) —
    the outstanding direction has no such reason, and losing it makes "branch here and try
    again" quietly different from carrying on."""
    from app.models import PlaySession

    scid, sid = _played(client, storyline_id, monkeypatch)
    turns = [e for e in _history(client, scid, sid)["events"] if e["type"] == "user_turn"]

    row = db_session.get(PlaySession, sid)
    row.standing_direction = [
        {"id": "before", "text": "Have Mei name the ledger.", "fromTurn": turns[0]["seq"]},
        {"id": "after", "text": "Have the lamp go over.", "fromTurn": turns[1]["seq"]},
    ]
    db_session.add(row)
    db_session.commit()

    fork = client.post(
        f"/api/play/{scid}/sessions/{sid}/branch", json={"atEventId": turns[0]["id"]}
    ).json()

    db_session.expire_all()
    inherited = db_session.get(PlaySession, fork["id"]).standing_direction or []
    # Only what was owed at or before the fork point — the later debt belongs to a turn the
    # fork never inherited.
    assert [r["id"] for r in inherited] == ["before"]
    # The parent keeps both.
    assert len(db_session.get(PlaySession, sid).standing_direction) == 2
