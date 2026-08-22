"""The scene can *ask* for an absent character. It can never bring one in.

The owner's rule: "it needs to be manually approved... I feel like the AI will abuse it and
bring in a character for the fun of it when we don't need it."

So the rule is made structural rather than merely intended. There is **no planner action**
that introduces a character — the engine's only move is to emit a `cast_request`, which
changes nothing. Presence moves through the ordinary manual `character_status_change` path,
and only when the player answers. These tests pin the three things that make that true: the
ask fires only when the *player* named someone, it fires at most once per character, and it
alters nothing by itself.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _route(monkeypatch, *, requirements=None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            return _resp(json.dumps({"requirements": requirements or []}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "role-playing AS a specific character" in system:
            return _resp(json.dumps({"choices": []}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The room shifts.")
        return _resp('<speaker:1>\n<type:character_dialogue>\n"A line."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _world(client, storyline_id):
    """Mei is cast in the scene; Kael exists in the world but is not in it."""
    mei = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    kael = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Kael"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [mei], "settingId": sid, "maxTurns": 3},
    ).json()["id"]
    return mei, kael, scid


def _turn(client, scid, body):
    events = []
    with client.stream("POST", f"/api/play/{scid}/turn", json={**body, "trace": True}) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _requests(events):
    return [e for e in events if e.get("type") == "cast_request"]


def test_naming_an_absent_character_asks_for_them(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, requirements=[{"actor": None, "must": "Kael bursts in"}])
    _mei, kael, scid = _world(client, storyline_id)

    events = _turn(client, scid, {"text": "", "guidance": "Kael bursts in"})
    asks = _requests(events)
    assert len(asks) == 1
    assert asks[0]["data"]["characterId"] == kael
    # The reason quotes the player's own words rather than a generic prompt.
    assert asks[0]["data"]["reason"] == "Kael bursts in"


def test_the_ask_changes_nothing_on_its_own(client, storyline_id, monkeypatch):
    """The whole point. A request is a question; presence is untouched until answered."""
    _configure_llm(client)
    _route(monkeypatch, requirements=[{"actor": None, "must": "Kael bursts in"}])
    _mei, kael, scid = _world(client, storyline_id)

    events = _turn(client, scid, {"text": "", "guidance": "Kael bursts in"})
    assert _requests(events)
    # No presence event was written…
    presence = [e for e in events if e.get("type") == "character_status_change"]
    assert presence == []
    # …and Kael did not speak.
    prose = [e for e in events if e.get("type") == "character_prose"]
    assert all(e["data"]["characterId"] != kael for e in prose)


def test_a_direction_naming_nobody_absent_asks_for_nothing(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, requirements=[{"actor": None, "must": "the lamp goes over"}])
    _mei, _kael, scid = _world(client, storyline_id)
    assert _requests(_turn(client, scid, {"text": "", "guidance": "The lamp goes over."})) == []


def test_a_character_already_in_the_scene_is_never_asked_about(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, requirements=[{"actor": None, "must": "Mei backs down"}])
    _mei, _kael, scid = _world(client, storyline_id)
    assert _requests(_turn(client, scid, {"text": "", "guidance": "Mei backs down"})) == []


def test_a_declined_character_is_not_asked_about_again(client, storyline_id, monkeypatch):
    """"Not now" is written as a presence change precisely so it leaves a mark. Without one
    the same ask would be re-offered every single turn the name appeared."""
    _configure_llm(client)
    _route(monkeypatch, requirements=[{"actor": None, "must": "Kael bursts in"}])
    _mei, kael, scid = _world(client, storyline_id)

    _turn(client, scid, {"text": "", "guidance": "Kael bursts in"})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    # The player declines.
    resp = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": psid, "characterId": kael, "status": "departed", "reason": "declined"},
    )
    assert resp.status_code == 200

    again = _turn(client, scid, {"text": "", "guidance": "Kael bursts in", "sessionId": psid})
    assert _requests(again) == []


def test_an_accepted_character_joins_the_scene_for_real(client, storyline_id, monkeypatch):
    """Accepting is the ordinary manual presence path, and the guest then appears in the
    cast the engine assembles — without the scenario row being touched."""
    _configure_llm(client)
    _route(monkeypatch, requirements=[])
    mei, kael, scid = _world(client, storyline_id)

    _turn(client, scid, {"text": "Hello."})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    resp = client.post(
        f"/api/play/{scid}/presence",
        json={"sessionId": psid, "characterId": kael, "status": "present"},
    )
    assert resp.status_code == 200

    events = _turn(client, scid, {"text": "Who else is here?", "sessionId": psid})
    assemble = next(
        e for e in events if e.get("type") == "trace" and e.get("step") == "assemble"
    )
    assert kael in [c["id"] for c in assemble["data"]["cast"]]

    # The authored scenario is unchanged — a guest belongs to the play-through.
    scenarios = client.get(f"/api/storylines/{storyline_id}/scenarios").json()
    row = next(s for s in scenarios if s["id"] == scid)
    assert row["castIds"] == [mei]
