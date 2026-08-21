"""The turn loop executes a multi-beat plan and re-plans only when it goes stale.

EXP-2026-08-005 attributed 41 % of turn time to the beat planner, entirely because it ran
once per beat. The engine now asks for several at once (``TURN_PLANNER_LOOKAHEAD``) and
consumes the queue. These tests pin the two halves that matter: the calls really are
fewer, and a plan is never executed against a roster it no longer describes.
"""

from __future__ import annotations

import json
import re

import httpx

from app.agents import planner_agent
from app.agents.planner_agent import BeatDecision
from app.services import llm


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _patch_llm(monkeypatch):
    """Everything but the planner, which the tests drive directly."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The room holds its breath.")
        # Echo whichever roster slot the prompt is voicing, so attribution is real.
        m = re.search(r"You are \[(\d+)\]", user)
        num = m.group(1) if m else "1"
        return _resp(f'<speaker:{num}>\n<type:character_dialogue>\n"Something is said."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _cast(client, storyline_id):
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [mei, kira], "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return mei, kira, scid


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_one_planner_call_covers_several_beats(client, storyline_id, monkeypatch):
    """Lookahead still works when an operator opts into it.

    It is **not** the default: the loop goes back and forth one beat at a time so the
    planner sees what each beat actually did. This pins the mechanism, not the default.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "turn_planner_lookahead", 3)
    _configure_llm(client)
    mei, kira, scid = _cast(client, storyline_id)
    _patch_llm(monkeypatch)

    calls: list[int] = []

    def fake_plan_beats(db, ctx, intent, turn_beats, acted, *, lookahead=1, **_kw):
        calls.append(lookahead)
        if len(calls) == 1:
            return [
                BeatDecision("narrate", reason="open"),
                BeatDecision("speak", actor_id=mei, reason="reacts"),
                BeatDecision("speak", actor_id=kira, reason="answers"),
            ]
        return [BeatDecision("end", reason="done")]

    monkeypatch.setattr(planner_agent, "plan_beats", fake_plan_beats)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Speak up."}))

    assert all(e["type"] != "error" for e in events)
    # Three beats ran, but the planner was consulted twice — once for the plan, once when
    # the queue emptied. The old loop would have called it four times.
    assert len(calls) == 2
    assert calls[0] > 1  # the lookahead actually reached the agent
    spoke = {e["data"]["characterId"] for e in events if e["type"] == "character_dialogue"}
    assert spoke == {mei, kira}


def test_a_plan_is_dropped_once_its_speaker_has_left(client, storyline_id, monkeypatch):
    """A beat planned before an exit must not run after it."""
    _configure_llm(client)
    mei, kira, scid = _cast(client, storyline_id)
    _patch_llm(monkeypatch)

    def fake_plan_beats(db, ctx, intent, turn_beats, acted, *, lookahead=1, **_kw):
        # Kira walks out, and the *same* plan then asks her to speak.
        return [
            BeatDecision("exit", actor_id=kira, status="left", reason="storms out"),
            BeatDecision("speak", actor_id=kira, reason="stale — she is gone"),
            BeatDecision("speak", actor_id=mei, reason="still here"),
            BeatDecision("end"),
        ]

    monkeypatch.setattr(planner_agent, "plan_beats", fake_plan_beats)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Say something."}))

    assert all(e["type"] != "error" for e in events)
    spoke = [e["data"]["characterId"] for e in events if e["type"] == "character_dialogue"]
    assert kira not in spoke  # the stale beat was never run
    assert mei in spoke


def test_lookahead_of_one_restores_the_per_beat_loop(client, storyline_id, monkeypatch):
    """The escape hatch has to actually work — this is the rollback path."""
    from app.core.config import get_settings

    _configure_llm(client)
    mei, _kira, scid = _cast(client, storyline_id)
    _patch_llm(monkeypatch)
    monkeypatch.setattr(get_settings(), "turn_planner_lookahead", 1)

    depths: list[int] = []

    def fake_plan_beats(db, ctx, intent, turn_beats, acted, *, lookahead=1, **_kw):
        depths.append(lookahead)
        return [BeatDecision("speak", actor_id=mei)] if len(depths) == 1 else [BeatDecision("end")]

    monkeypatch.setattr(planner_agent, "plan_beats", fake_plan_beats)
    _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Go."}))
    assert depths and set(depths) == {1}
