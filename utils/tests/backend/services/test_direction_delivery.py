"""Attempted is not delivered — the largest cause of a direction being "forgotten".

The engine used to mark a requirement satisfied at the moment it put that requirement into a
prompt. That is a promise, not an outcome: a beat that came back empty, was withheld as a
scratchpad leak, or failed against the endpoint still ticked the requirement off for good.
Observed live before the fix — the trace read "The narrator delivered 1 part(s) of your
direction" on a turn where **zero** beats were persisted.

These run the real turn loop against a mocked endpoint, so the assertions are about what the
engine does with a beat's actual output rather than about the coverage arithmetic (which is
pinned separately in ``test_direction_check.py``).
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


def _route(monkeypatch, *, requirements, narrator: str, decisions=()):
    """Route the mock by system prompt, with the narrator's prose scripted per test."""
    plan = iter(decisions)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            return _resp(json.dumps({"requirements": requirements}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "role-playing AS a specific character" in system:
            return _resp(json.dumps({"choices": []}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp(narrator)
        return _resp('<speaker:1>\n<type:character_dialogue>\n"Something else entirely."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _scenario(client, storyline_id, *, max_turns=4):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid, "maxTurns": max_turns},
    ).json()["id"]


def _traces(events, step):
    return [e for e in events if e.get("type") == "trace" and e.get("step") == step]


def _turn(client, scid, guidance):
    events = []
    with client.stream(
        "POST", f"/api/play/{scid}/turn", json={"text": "", "guidance": guidance, "trace": True}
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


REQ = [{"actor": None, "must": "the lamp goes over"}]


def test_a_beat_that_returns_nothing_leaves_its_requirement_outstanding(
    client, storyline_id, monkeypatch
):
    """The failure case, and the one that needs no heuristic at all.

    An empty narrator reply emits no beat, so there is no prose to confirm against and the
    requirement simply stays owed. Before the split it was ticked off anyway.
    """
    _configure_llm(client)
    _route(monkeypatch, requirements=REQ, narrator="")
    scid = _scenario(client, storyline_id)
    events = _turn(client, scid, "The lamp goes over.")

    summary = _traces(events, "direction")[-1]
    assert summary["data"]["delivered"] == 0
    assert "the lamp goes over" in summary["data"]["undelivered"]
    # Nothing may claim it was delivered anywhere on the stream.
    assert not any(t["data"].get("delivered") for t in _traces(events, "direction")[:-1])


def test_prose_that_covers_the_requirement_confirms_it(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, requirements=REQ, narrator="The lamp goes over with a crash.")
    scid = _scenario(client, storyline_id)
    events = _turn(client, scid, "The lamp goes over.")

    summary = _traces(events, "direction")[-1]
    assert summary["data"]["delivered"] == 1
    assert summary["data"]["undelivered"] == []
    assert summary["title"] == "Your direction was delivered in full"


def test_prose_about_something_else_is_attempted_not_delivered(
    client, storyline_id, monkeypatch
):
    """The case the old code could not see: a beat that ran, produced prose, and simply did
    not do the thing. It is reported as *unconfirmed* rather than delivered or never-tried —
    a beat did aim at it, and the check being crude is as likely an explanation as failure."""
    _configure_llm(client)
    _route(monkeypatch, requirements=REQ, narrator="They talk quietly about the weather.")
    scid = _scenario(client, storyline_id)
    events = _turn(client, scid, "The lamp goes over.")

    summary = _traces(events, "direction")[-1]
    assert summary["data"]["delivered"] == 0
    assert summary["data"]["unconfirmed"] == ["the lamp goes over"]
    # Never-reached is the OTHER bucket, and this is not it.
    assert summary["data"]["never"] == []


def test_an_unconfirmed_requirement_is_retried_and_then_stops(
    client, storyline_id, monkeypatch
):
    """Bounded by DIRECTION_MAX_ATTEMPTS (2). Without the cap, a requirement the lexical
    check cannot see would be re-owed to every remaining beat of the scene."""
    _configure_llm(client)
    _route(monkeypatch, requirements=REQ, narrator="They talk quietly about the weather.")
    scid = _scenario(client, storyline_id, max_turns=6)
    events = _turn(client, scid, "The lamp goes over.")

    attempts = [t for t in _traces(events, "direction") if t["data"].get("attempted")]
    assert len(attempts) == 2, "tried twice, then left alone"
    assert _traces(events, "direction")[-1]["data"]["unconfirmed"] == ["the lamp goes over"]
