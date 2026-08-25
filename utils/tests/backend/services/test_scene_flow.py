"""`sceneFlow` — one call per speaker, or one call for the whole turn.

`"voiced"` is what has always shipped and is the default: every scene written before this
column, and every request that does not mention it, runs exactly as it did. `"continuous"`
writes the planned turn in one generation and marks each change of speaker.

The tests that matter here are the ones about **degrading**. Continuous prose is a bet — it
trades per-character prompt isolation for flow, and the owner asked for it to be foolproof on
less intelligent models. A model that cannot emit the speaker tokens must fall back to today's
behaviour, never to something worse: one long passage attributed to whoever was first is a
mis-attributed monologue, not a scene.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import scene_script_agent
from app.models import Scenario
from app.services import llm, turn_settings


# ---- the setting resolves conservatively ------------------------------------


def test_a_scene_that_never_set_it_is_voiced():
    """NULL reads as `voiced`, so no existing scene changes behaviour."""
    assert turn_settings.resolve(Scenario(suggestions_count=4)).scene_flow == "voiced"


def test_an_unrecognised_value_falls_back_rather_than_raising():
    """The schema guards the request boundary; this guards a hand-edited or imported row."""
    assert turn_settings.resolve(Scenario(scene_flow="interpretive-dance")).scene_flow == "voiced"


def test_a_turn_may_override_the_scene():
    from app.schemas.play import TurnOverrides

    resolved = turn_settings.resolve(
        Scenario(scene_flow="voiced"), TurnOverrides(sceneFlow="continuous")
    )
    assert resolved.scene_flow == "continuous"


# ---- the fallback -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "speakers", "expected"),
    [
        ("No tags at all, just one long passage.", 3, True),
        ("First beat.\n<speaker:2>\nSecond beat.", 3, False),
        # One speaker was planned, so there was never a hand-off to emit. Falling back here
        # would re-run a turn that came out exactly right.
        ("A single character's passage.", 1, False),
        ("", 3, True),
    ],
)
def test_looks_unscripted_only_fires_when_a_hand_off_was_expected_and_missing(
    raw, speakers, expected
):
    assert scene_script_agent.looks_unscripted(raw, expected_speakers=speakers) is expected


def test_a_partly_tagged_script_is_not_thrown_away():
    """Deliberately lenient.

    A script that emitted three hand-offs of four is still a scene. Re-running the whole turn
    to chase the fourth costs a full generation to fix one beat's attribution, which is a
    worse trade than the beat.
    """
    raw = "One.\n<speaker:2>\nTwo.\nThree, also somehow speaker two.\n"
    assert scene_script_agent.looks_unscripted(raw, expected_speakers=3) is False


# ---- end to end -------------------------------------------------------------


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _route(monkeypatch, script: str, counter: dict):
    """Route by system prompt; `script` is what the scene-script agent returns."""
    counter.setdefault("script", 0)
    counter.setdefault("character", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "one scene of a novel" in system:
            counter["script"] += 1
            return _resp(script)
        if "step-by-step loop" in system:
            return _resp(json.dumps({"beats": [
                {"action": "speak", "actor": 1},
                {"action": "speak", "actor": 2},
                {"action": "end"},
            ]}))
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
        counter["character"] += 1
        return _resp('"I hear you," I say.')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _scene(client, storyline_id):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in ("Lily", "Zoe")
    ]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Flow", "castIds": ids, "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return scid, ids


def test_a_continuous_turn_attributes_each_hand_off_to_its_own_speaker(
    client, storyline_id, monkeypatch
):
    """The whole point: the speaker-change signal the client needs is the event boundary.

    Each run of the script opens its own event with its own `characterId`, so the frontend
    needs no new contract to know the speaker changed — which is why this phase is
    backend-only.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(
        monkeypatch,
        "I am up on the table before anyone can stop me.\n<speaker:2>\nI catch her by the hem.",
        counter,
    )
    scid, ids = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Go.", "overrides": {"sceneFlow": "continuous"}},
        )
    )
    prose = [e for e in events if e.get("type") == "character_prose"]
    assert counter["script"] == 1, "one call writes the whole turn"
    assert counter["character"] == 0, "and the per-speaker writer is not called at all"
    assert {e["data"]["characterId"] for e in prose} == set(ids)


def test_a_script_with_no_hand_offs_falls_back_to_the_per_speaker_path(
    client, storyline_id, monkeypatch
):
    """The foolproof requirement, and the reason the fallback exists.

    A model that ignores the token format returns one passage. Parsed, that is a single beat
    attributed to whoever was first — worse than what the voiced path would have produced, so
    the turn re-runs that way instead.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, "One long passage with no tags in it whatsoever.", counter)
    scid, _ids = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Go.", "trace": True, "overrides": {"sceneFlow": "continuous"}},
        )
    )
    assert counter["script"] == 1
    assert counter["character"] > 0, "the per-speaker writer took over"
    fallback = [
        t for t in events
        if t.get("type") == "trace" and t.get("data", {}).get("sceneFlow") == "fallback"
    ]
    assert fallback, "a silent fallback is a mode that looks broken rather than degraded"


def test_voiced_is_untouched_by_any_of_this(client, storyline_id, monkeypatch):
    """The default path must not call the script agent at all."""
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, "unused", counter)
    scid, _ids = _scene(client, storyline_id)

    _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Go."}))
    assert counter["script"] == 0
    assert counter["character"] > 0
