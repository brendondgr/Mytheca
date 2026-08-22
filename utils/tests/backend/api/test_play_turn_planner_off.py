"""POST /api/play/{scenarioId}/turn with planning switched off.

The claim this makes is a **negative** one — no model call decides who speaks — so it is
tested the only way a negative can be: ``planner_agent.plan_beats`` is monkeypatched to
raise, and a turn that touches it fails loudly instead of quietly costing what the player
asked to stop paying.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.services import llm

_EMISSION = '<speaker:1>\n"Someone speaks."'


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch):
    """Answer every non-planner agent; the planner is barred separately below."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("A hush falls.")
        return _resp(_EMISSION)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _bar_the_planner(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("plan_beats was called with planning switched off")

    monkeypatch.setattr(planner_agent, "plan_beats", explode)


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _scene(client, storyline_id, names=("Ana", "Bo", "Cy"), **scenario):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in names
    ]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}
    ).json()["id"]
    body = {"title": "Off", "castIds": ids, "settingId": sid, **scenario}
    return client.post(f"/api/storylines/{storyline_id}/scenarios", json=body).json()["id"], ids


def _prose_count(events: list[dict]) -> int:
    return len({e["id"] for e in events if e["type"] == "character_prose"})


def test_a_planner_off_turn_produces_beats_without_calling_the_planner(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _bar_the_planner(monkeypatch)
    scid, ids = _scene(client, storyline_id, maxTurns=5)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I address the room.",
                "directedAt": ids[0],
                "trace": True,
                "overrides": {"planner": "off"},
            },
        )
    )

    assert _prose_count(events) >= 1
    assert all(e["type"] != "error" for e in events)


def test_the_trace_says_planning_is_off(client, storyline_id, monkeypatch):
    """A fast turn must not read as a broken one."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _bar_the_planner(monkeypatch)
    scid, ids = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "Hello.",
                "directedAt": ids[0],
                "trace": True,
                "overrides": {"planner": "off"},
            },
        )
    )

    step = next(
        t for t in events if t["type"] == "trace" and t["step"] == "planning"
    )
    assert "planning off" in step["title"].lower()
    assert step["data"]["planner"] == "off"


def test_the_scene_cap_still_applies(client, storyline_id, monkeypatch):
    """The cap is the engine's rule, not the planner's, so switching the planner off must
    not switch it off too."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _bar_the_planner(monkeypatch)
    scid, ids = _scene(client, storyline_id, names=("Ana", "Bo", "Cy", "Di"), maxTurns=2)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I address the room.",
                "directedAt": ids[0],
                "overrides": {"planner": "off"},
            },
        )
    )

    assert _prose_count(events) <= 2


def test_the_scene_can_default_to_planning_off(client, storyline_id, monkeypatch):
    """`plannerMode` on the row, with no per-turn override."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _bar_the_planner(monkeypatch)
    scid, ids = _scene(client, storyline_id, plannerMode="off")

    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Hi.", "directedAt": ids[0]})
    )

    assert _prose_count(events) >= 1


def test_a_per_turn_override_beats_a_scene_set_to_planner(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _bar_the_planner(monkeypatch)
    scid, ids = _scene(client, storyline_id, plannerMode="planner")

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Hi.", "directedAt": ids[0], "overrides": {"planner": "off"}},
        )
    )

    assert _prose_count(events) >= 1


def test_planner_mode_round_trips_and_rejects_nonsense(client, storyline_id):
    scid, _ = _scene(client, storyline_id)
    assert client.get(f"/api/scenarios/{scid}").json()["plannerMode"] is None

    client.patch(f"/api/scenarios/{scid}", json={"plannerMode": "off"})
    assert client.get(f"/api/scenarios/{scid}").json()["plannerMode"] == "off"

    assert client.patch(f"/api/scenarios/{scid}", json={"plannerMode": "vibes"}).status_code == 422


@pytest.mark.parametrize("mode", [None, "planner"])
def test_the_planner_still_runs_by_default(client, storyline_id, monkeypatch, mode):
    """The negative test's mirror: if `plan_beats` were unreachable in every mode, the
    assertions above would prove nothing."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    called: list[bool] = []

    real = planner_agent.plan_beats

    def spy(*args, **kwargs):
        called.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr(planner_agent, "plan_beats", spy)
    scid, ids = _scene(client, storyline_id, **({"plannerMode": mode} if mode else {}))

    client.post(f"/api/play/{scid}/turn", json={"text": "Hi.", "directedAt": ids[0]})

    assert called
