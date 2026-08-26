"""An approved plan is a contract: the beats it names are the beats that run.

Before this, `turn_engine`'s `elif not planned:` branch re-planned whenever the queue
emptied, so an approved plan was a head start on an open-ended loop rather than an
agreement. `EXP-2026-08-016` measured the consequence — turns of 18, 22 and 24 beats, the
last being the runaway backstop rather than anybody's decision.

The property under test is a **count**, deliberately. "The plan is respected" is easy to
believe from a transcript that looks reasonable; only counting beats against the plan
catches a turn that ran the approved beats and then quietly added more.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import llm

pytestmark = pytest.mark.usefixtures("per_speaker_scenes")


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _route(monkeypatch, counter: dict):
    """Count planner calls. A bound turn must make exactly zero of them."""
    counter.setdefault("planner", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        system = json.loads(request.content.decode())["messages"][0]["content"]
        if "step-by-step loop" in system:
            counter["planner"] += 1
            # Deliberately says "keep going forever". A bound turn must ignore it entirely;
            # an unbound one would run to the backstop on this.
            return _resp(json.dumps({"beats": [{"action": "speak", "actor": 1}]}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return _resp(json.dumps({"choices": []}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The lamp gutters.")
        return _resp('"I hear you," she says.')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _scene(client, storyline_id):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in ("Lily", "Zoe")
    ]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Bound", "castIds": ids, "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return scid, ids


def _run(client, scid, approved):
    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Go.", "trace": True, "approvedPlan": approved,
              "overrides": {"sceneFlow": "voiced"}},
    )
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


#: Only the beats the plan named. The scene-opening narration is emitted to set the scene
#: before the plan runs and is deliberately NOT counted — every plan in this file is made of
#: `speak` beats, so counting character beats counts exactly the contract.
_CHARACTER = {"character_prose", "character_dialogue", "character_action"}


def _prose_beats(events) -> int:
    """Unique beats, by event id.

    Delta frames re-emit the SAME id with incremental text, so counting frames would count
    every beat twice over.
    """
    return len({e["id"] for e in events if e.get("type") in _CHARACTER})


@pytest.mark.parametrize("n", [2, 3, 8])
def test_a_plan_of_n_beats_runs_exactly_n_beats(client, storyline_id, monkeypatch, n):
    """3 means 3 and 8 means 8 — the owner's requirement, stated as a count.

    ``n = 1`` is excluded and covered separately below: a single-beat plan on a two-character
    scene trips the EXCHANGE FLOOR, which adds a beat so a room with two people in it does not
    answer the player with one line. That floor predates this work and guards a reported
    failure, so it is asserted rather than suppressed.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, counter)
    scid, ids = _scene(client, storyline_id)

    approved = [{"action": "speak", "actorId": ids[i % len(ids)]} for i in range(n)]
    events = _run(client, scid, approved)

    assert _prose_beats(events) == n
    assert counter["planner"] == 0, "a bound turn must not consult the planner at all"


def test_the_turn_ends_at_the_plan_rather_than_re_planning(client, storyline_id, monkeypatch):
    """The regression this file exists for.

    The mock planner always answers "one more beat". If the engine asks it anything once the
    approved beats are spent, the turn runs away to the backstop — which is exactly what
    EXP-2026-08-016 recorded.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, counter)
    scid, ids = _scene(client, storyline_id)

    events = _run(client, scid, [{"action": "speak", "actorId": ids[0]},
                                 {"action": "speak", "actorId": ids[1]}])

    assert _prose_beats(events) == 2
    assert counter["planner"] == 0
    done = [
        e for e in events
        if e.get("type") == "trace" and (e.get("data") or {}).get("bound") is True
    ]
    assert done, "the turn must say it stopped because the plan was complete"


def test_the_exchange_floor_still_outranks_a_one_beat_plan(client, storyline_id, monkeypatch):
    """A bound plan does NOT repeal the engine's floors, and that is deliberate.

    A one-beat plan on a two-character scene would leave somebody in the room answering the
    player with silence — the reported failure that put the exchange floor there
    (`test_play_turn_exchange.py`). Binding is about stopping the loop from inventing beats
    the planner never asked for; it is not licence to drop a guarantee that predates it.

    Whether the plan SHOULD outrank that floor is an open product question recorded in
    `docs/checklist.md`. This test pins today's answer so a change to it has to be a decision.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, counter)
    scid, ids = _scene(client, storyline_id)

    events = _run(client, scid, [{"action": "speak", "actorId": ids[0]}])

    assert _prose_beats(events) == 2, "the floor added the second character's answer"
    assert counter["planner"] == 0, "and it did so WITHOUT re-planning"


def test_an_unbound_turn_is_untouched(client, storyline_id, monkeypatch):
    """The change must not turn ordinary `auto` turns into one-beat turns."""
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, counter)
    scid, _ids = _scene(client, storyline_id)

    _run(client, scid, [])
    assert counter["planner"] > 0, "a turn with no approved plan still plans for itself"
