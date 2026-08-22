"""Re-roll a beat — another version, in place, with the previous one kept.

Two properties carry the feature:

* the re-take lands in the **same transcript position** (same event id and seq), rather than
  being appended to the end of the scene;
* the previous wording is **kept as a take**, because the player asked for a different line,
  not for the one they already read to stop existing — and often the first was better.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_FIRST = (
    "<speaker:1>\n"
    "<thinking>Hold steady.</thinking>\n"
    "Mei sets the cup down.\n"
    '"Say that again."'
)
_SECOND = (
    "<speaker:1>\n"
    "<thinking>Let it go.</thinking>\n"
    "Mei turns away from the table.\n"
    '"Forget I asked."'
)


def _patch_llm(monkeypatch, content):
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


def _played(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, _FIRST)
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    with client.stream("POST", f"/api/play/{scid}/turn", json={"text": "Go on."}) as r:
        for _ in r.iter_lines():
            pass
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    return scid, psid


def _events(client, scid, psid):
    return client.get(f"/api/play/{scid}/sessions/{psid}").json()["events"]


def _beat(client, scid, psid, type_="character_prose"):
    return next(e for e in _events(client, scid, psid) if e["type"] == type_)


def _reroll(client, scid, psid, event_id, scope="beat"):
    frames = []
    with client.stream(
        "POST",
        f"/api/play/{scid}/sessions/{psid}/beats/{event_id}/reroll",
        json={"scope": scope},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.strip():
                frames.append(json.loads(line))
    return frames


def test_a_reroll_keeps_the_beats_id_and_position(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    before = [(e["id"], e["seq"]) for e in _events(client, scid, psid)]

    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"])

    after = [(e["id"], e["seq"]) for e in _events(client, scid, psid)]
    # The transcript's shape is unchanged: a re-roll replaces, it does not append.
    assert after == before


def test_a_reroll_replaces_the_visible_text(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    assert "Say that again." in beat["data"]["text"]

    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"])

    again = next(e for e in _events(client, scid, psid) if e["id"] == beat["id"])
    assert "Forget I asked." in again["data"]["text"]


def test_a_reroll_keeps_the_previous_wording_as_a_take(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    original = beat["data"]["text"]

    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"])

    data = next(e for e in _events(client, scid, psid) if e["id"] == beat["id"])["data"]
    assert len(data["takes"]) == 2
    assert data["takes"][0]["text"] == original      # the line the player already read
    assert data["activeTake"] == 1
    assert data["text"] == data["takes"][1]["text"]  # `text` mirrors the active take


def test_the_stream_leads_with_a_clear_instruction(client, storyline_id, monkeypatch):
    """Without it the deltas would append to the take being replaced."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)

    _patch_llm(monkeypatch, _SECOND)
    frames = _reroll(client, scid, psid, beat["id"])

    assert frames[0]["type"] == "beat_reroll"
    assert frames[0]["eventId"] == beat["id"]


def test_flipping_back_to_an_earlier_take(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    original = beat["data"]["text"]
    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"])

    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}/take", json={"take": 0}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["text"] == original
    assert resp.json()["data"]["activeTake"] == 0


def test_selecting_a_take_that_does_not_exist_is_refused(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"])

    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}/take", json={"take": 9}
    )
    assert resp.status_code == 422


def test_a_beat_with_one_version_has_no_pager(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}/take", json={"take": 0}
    )
    assert resp.status_code == 422


def test_a_machinery_beat_cannot_be_rerolled(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    turn = _beat(client, scid, psid, "user_turn")
    frames = _reroll(client, scid, psid, turn["id"])
    assert frames[-1]["type"] == "error"


def test_rerolling_a_beat_from_another_play_through_404s(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    other = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    beat = _beat(client, scid, psid)
    resp = client.post(
        f"/api/play/{scid}/sessions/{other}/beats/{beat['id']}/reroll", json={"scope": "beat"}
    )
    assert resp.status_code == 404


def test_a_turn_scope_reroll_replays_the_whole_turn(client, storyline_id, monkeypatch):
    """The owner asked for both scopes: a beat that went wrong because the TURN went wrong is
    not fixed by re-rolling one line of it."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)

    _patch_llm(monkeypatch, _SECOND)
    _reroll(client, scid, psid, beat["id"], scope="turn")

    events = _events(client, scid, psid)
    # The player's line survived the replay (it was replayed, not discarded)…
    turns = [e for e in events if e["type"] == "user_turn"]
    assert [t["data"]["text"] for t in turns] == ["Go on."]
    # …and the scene was rewritten from the new generation.
    prose = " ".join(e["data"].get("text", "") for e in events if e["type"] == "character_prose")
    assert "Forget I asked." in prose


def test_reroll_409s_on_a_stale_expected_seq(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _beat(client, scid, psid)
    resp = client.post(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}/reroll",
        json={"scope": "beat", "expectedSeq": 0},
    )
    assert resp.status_code == 409


def test_a_reroll_does_not_re_apply_the_beats_consequences(client, storyline_id, monkeypatch):
    """A re-take changes the wording, not the world.

    The original beat's stat change already happened and is recorded. Applying the new take's
    as well would drift the character a little further every time the player asked for a
    different line, and stack a fresh `state_update` row onto the scene each time.
    """
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "trust", "displayName": "Trust", "min": 0, "max": 100, "default": 50},
    )
    _patch_llm(monkeypatch, _FIRST + '\n<type:state_update>\n{"key":"trust","delta":10}')
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    with client.stream("POST", f"/api/play/{scid}/turn", json={"text": "Go on."}) as r:
        for _ in r.iter_lines():
            pass
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    before = [e["type"] for e in _events(client, scid, psid)]
    beat = _beat(client, scid, psid)

    _patch_llm(monkeypatch, _SECOND + '\n<type:state_update>\n{"key":"trust","delta":10}')
    _reroll(client, scid, psid, beat["id"])

    after = [e["type"] for e in _events(client, scid, psid)]
    # The transcript's shape is byte-identical: no extra state_update was appended.
    assert after == before
