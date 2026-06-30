"""POST /api/play/{scenarioId}/turn — streaming turn transport (P1 echo)."""

from __future__ import annotations

import json

from app.events import story_event_adapter


def _refs(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Smoldering Hearth"}
    ).json()["id"]
    return cid, sid


def _scenario(client, storyline_id, cast, setting):
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": cast, "settingId": setting},
    ).json()["id"]


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_turn_streams_a_valid_event_set(client, storyline_id):
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "I slide the coin pouch toward Mei.", "directedAt": cid},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    events = _stream(resp)
    types = [e["type"] for e in events]
    assert "narration" in types and "character_dialogue" in types
    for e in events:
        assert e["scenarioId"] == scid and e["sessionId"] and e["id"] and e["ts"]
    dia = next(e for e in events if e["type"] == "character_dialogue")
    assert dia["data"]["characterId"] == cid  # the addressed character speaks


def test_streamed_lines_validate_against_the_adapter(client, storyline_id):
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})
    for e in _stream(resp):
        story_event_adapter.validate_python(e)  # every streamed line is a valid story event


def test_seq_is_monotonic_and_unique(client, storyline_id):
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    assert min(seqs) >= 1  # seq 0 is the persisted user_turn (not streamed)


def test_session_resumes_and_seq_continues(client, storyline_id):
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    first = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "one", "directedAt": cid}))
    session_id = first[0]["sessionId"]
    second = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "two", "directedAt": cid, "sessionId": session_id},
        )
    )
    assert all(e["sessionId"] == session_id for e in second)
    assert min(e["seq"] for e in second) > max(e["seq"] for e in first)


def test_no_cast_still_streams_narration(client, storyline_id):
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hello"}))
    assert [e["type"] for e in events] == ["narration"]


def test_unknown_scenario_returns_404(client):
    resp = client.post("/api/play/nope/turn", json={"text": "hi"})
    assert resp.status_code == 404


def test_empty_text_returns_400(client, storyline_id):
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "   "})
    assert resp.status_code == 400


def test_unknown_session_returns_404(client, storyline_id):
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "hi", "sessionId": "ps_missing"})
    assert resp.status_code == 404
