"""Explicit directives — the player names the target, so nothing is guessed.

The direction box is read per line, and an `@` cast mention on a line pins that line to that
character. When the client sends those, the engine has nothing left to infer: spending an LLM
round-trip to re-derive what the player already stated is both slower and worse.

The other half is that a target the player set is **never** silently re-owned. Before this,
`rebind()` handed any requirement whose character was absent — or who was the POV character —
straight to the narrator, on every pass of the beat loop. A guess deserves that rescue; an
instruction does not.
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


def _route(monkeypatch, log: dict, *, narrator="The room shifts."):
    log.setdefault("direction_calls", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            log["direction_calls"] += 1
            return _resp(json.dumps({"requirements": []}))
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
            return _resp(narrator)
        return _resp('<speaker:1>\n<type:character_dialogue>\n"A line."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _two(client, storyline_id):
    mei = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    kira = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    return mei, kira, sid


def _scenario(client, storyline_id, cast, sid, *, max_turns=3):
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": cast, "settingId": sid, "maxTurns": max_turns},
    ).json()["id"]


def _stream(client, scid, body):
    events = []
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _traces(events, step):
    return [e for e in events if e.get("type") == "trace" and e.get("step") == step]


def test_directives_are_used_verbatim_with_no_parse_call(client, storyline_id, monkeypatch):
    """The whole reason the field exists: the player already said what and who."""
    _configure_llm(client)
    log: dict = {}
    _route(monkeypatch, log)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    events = _stream(client, scid, {
        "text": "",
        "guidance": "Mei backs down\nthe lamp goes over",
        "directives": [
            {"text": "Mei backs down", "actorId": mei},
            {"text": "the lamp goes over", "actorId": None},
        ],
        "trace": True,
    })

    assert log["direction_calls"] == 0, "nothing left to infer, so no round-trip"
    opening = _traces(events, "direction")[0]
    assert opening["data"]["source"] == "directives"
    assert [r["text"] for r in opening["data"]["requirements"]] == [
        "Mei backs down",
        "the lamp goes over",
    ]
    # Only the one the player aimed is pinned.
    assert [r["pinned"] for r in opening["data"]["requirements"]] == [True, False]
    assert opening["data"]["requirements"][0]["actor"] == "Mei"


def test_a_pinned_target_is_not_handed_to_the_narrator_under_pov(
    client, storyline_id, monkeypatch
):
    """The bug this fixes: under POV, everything the player aimed at their OWN character was
    instantly re-owned to the narrator, because the AI does not voice them. The AI not
    voicing them does not mean the requirement cannot be met."""
    _configure_llm(client)
    log: dict = {}
    _route(monkeypatch, log)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    events = _stream(client, scid, {
        "text": "I stand my ground.",
        "povCharacterId": mei,
        "guidance": "Mei backs down",
        "directives": [{"text": "Mei backs down", "actorId": mei}],
        "trace": True,
    })

    opening = _traces(events, "direction")[0]
    assert opening["data"]["requirements"][0]["actor"] == "Mei", "still hers"
    assert opening["data"]["requirements"][0]["pinned"] is True


def test_an_unpinned_target_is_still_rescued(client, storyline_id, monkeypatch):
    """A *guess* still gets the narrator rescue — only an instruction is protected."""
    _configure_llm(client)
    log: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            return _resp(json.dumps({"requirements": [{"actor": 1, "must": "Mei backs down"}]}))
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
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    events = _stream(client, scid, {
        "text": "I hesitate.",
        "povCharacterId": mei,
        "guidance": "Mei backs down",
        "trace": True,
    })
    opening = _traces(events, "direction")[0]
    assert opening["data"]["requirements"][0]["actor"] is None
    assert opening["data"]["requirements"][0]["pinned"] is False


def test_a_pinned_target_who_is_absent_waits_rather_than_being_reassigned(
    client, storyline_id, monkeypatch
):
    """"Kira does X" where Kira is not in this scene is not something the narrator can be
    handed — the player asked for *that* person. It waits, says so, and is carried over."""
    _configure_llm(client)
    log: dict = {}
    _route(monkeypatch, log)
    mei, kira, sid = _two(client, storyline_id)
    # Kira exists in the storyline but is NOT in this scenario's cast.
    scid = _scenario(client, storyline_id, [mei], sid)

    events = _stream(client, scid, {
        "text": "",
        "guidance": "Kira bursts in",
        "directives": [{"text": "Kira bursts in", "actorId": kira}],
        "trace": True,
    })

    # A directive binds against the whole STORYLINE, not just the scene's cast — aiming a
    # line at someone who is not in the room is a legitimate thing to write, and it is the
    # case worth keeping rather than dropping.
    opening = _traces(events, "direction")[0]
    assert opening["data"]["source"] == "directives"
    assert opening["data"]["requirements"][0]["pinned"] is True
    assert opening["data"]["requirements"][0]["actor"] == "Kira"

    # It waits rather than being handed to the narrator, and says so.
    blocked = [t for t in _traces(events, "direction") if t["data"].get("blocked")]
    assert blocked, "the scene must say who it is waiting for"
    assert blocked[0]["data"]["characterName"] == "Kira"
    assert "not in the scene" in blocked[0]["title"]


def test_an_unknown_actor_id_is_dropped_not_guessed(client, storyline_id, monkeypatch):
    _configure_llm(client)
    log: dict = {}
    _route(monkeypatch, log)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei], sid)

    events = _stream(client, scid, {
        "text": "",
        "guidance": "someone reacts",
        "directives": [{"text": "someone reacts", "actorId": "ch_nonexistent"}],
        "trace": True,
    })
    opening = _traces(events, "direction")[0]
    assert opening["data"]["requirements"][0]["actor"] is None
    assert opening["data"]["requirements"][0]["pinned"] is False


def test_empty_directives_keep_todays_behaviour(client, storyline_id, monkeypatch):
    """A player who ignores the feature must see nothing change: free prose in the box is
    still parsed by the direction agent."""
    _configure_llm(client)
    log: dict = {}
    _route(monkeypatch, log)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    events = _stream(client, scid, {
        "text": "",
        "guidance": "Something happens.",
        "directives": [],
        "trace": True,
    })
    assert log["direction_calls"] == 1
    assert _traces(events, "direction")[0]["data"]["source"] == "guidance"
