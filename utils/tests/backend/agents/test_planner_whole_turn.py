"""The whole turn is planned in ONE call.

Planning per beat had three costs, and only the first was obvious: it made the plan
advisory (the loop re-planned whenever the queue emptied — see `test_bound_plan.py`), it
paid the planner's latency once per beat, and it thrashed the inference server's single KV
cache. `_build_user_prompt` is deliberately ordered STABLE -> APPEND-ONLY -> VOLATILE so a
scene's prefix stays warm across speakers; interleaving a differently-shaped planner prompt
between every beat overwrites exactly that prefix.

`plan_turn`'s contract is narrow on purpose: it reports whether the plan is *complete*, and
only a complete plan may be treated as binding. A plan produced by the fallback path (the
endpoint is down) must NOT bind, or a model outage becomes a one-beat scene.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.services import llm

pytestmark = pytest.mark.usefixtures("per_speaker_scenes")


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _route(monkeypatch, plan: dict, counter: dict):
    counter.setdefault("planner", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        system = json.loads(request.content.decode())["messages"][0]["content"]
        if "step-by-step loop" in system:
            counter["planner"] += 1
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(plan)}}]}
            )
        if "You interpret" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"kind": "freeform", "directive": "go"})}}]})
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"choices": []})}}]})
        if "continuity auditor" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"consistent": True})}}]})
        if "private inner voice" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        if "narrator of an interactive scene" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": "The lamp gutters."}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '"Yes," she says.'}}]})

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
        json={"title": "Once", "castIds": ids, "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return scid


def test_a_self_terminating_plan_is_planned_once_and_run(client, storyline_id, monkeypatch):
    """The property the owner asked for: one planning phase, then execution."""
    _configure_llm(client)
    counter: dict = {}
    plan = {"beats": [
        {"action": "speak", "actor": 1},
        {"action": "speak", "actor": 2},
        {"action": "speak", "actor": 1},
        {"action": "end"},
    ]}
    _route(monkeypatch, plan, counter)
    scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Go.", "trace": True, "overrides": {"sceneFlow": "voiced"}},
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    kinds = {"character_prose", "character_dialogue", "character_action"}
    beats = len({e["id"] for e in events if e.get("type") in kinds})

    assert counter["planner"] == 1, "the turn must be planned exactly once"
    assert beats == 3, "the three planned beats run, and nothing more"


def test_a_plan_without_a_trailing_end_still_binds(client, storyline_id, monkeypatch):
    """The regression EXP-2026-08-017's first run found.

    Binding used to require the planner to append an explicit `end`. It frequently does not,
    and a plan judged "incomplete" reverted to the adaptive loop: measured at **9 beats run
    against 3 planned**, with two planner calls. A plan the model wrote IS the turn.
    """
    _configure_llm(client)
    counter: dict = {}
    plan = {"beats": [{"action": "speak", "actor": 1}, {"action": "speak", "actor": 2}]}
    _route(monkeypatch, plan, counter)
    scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Go.", "trace": True, "overrides": {"sceneFlow": "voiced"}},
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    kinds = {"character_prose", "character_dialogue", "character_action"}
    beats = len({e["id"] for e in events if e.get("type") in kinds})

    assert counter["planner"] == 1, "no re-plan, even with no trailing end"
    assert beats == 2, "the two planned beats ran, and nothing more"


def test_a_fallback_plan_still_does_not_bind(db_session, monkeypatch):
    """The one case that must stay unbound.

    When the endpoint is unreachable `plan_beats` returns a single scripted beat. Binding
    THAT would turn a model outage into a one-beat scene, so the distinction is where the
    answer came from — not whether it happened to end with `end`.
    """
    from app.agents import planner_agent as pa

    source: dict = {}

    def fake_plan_beats(*_a, source_out=None, **_kw):
        if source_out is not None:
            source_out["source"] = "fallback"
        return [pa.BeatDecision("speak", actor_id="c1")]

    monkeypatch.setattr(pa, "plan_beats", fake_plan_beats)
    _decisions, complete = pa.plan_turn(
        db_session, object(), object(), [], [], budget=12,
    )
    assert complete is False
    assert source == {}
