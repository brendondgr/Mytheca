"""The beat register travels planner → turn engine → character prompt (end-to-end).

The planner already reads the moment once per beat, so the register costs no extra LLM
call — but it is only worth anything if it actually reaches the speaker's prompt. This
drives the real turn route with a system-prompt-routed mock: the planner call gets a
JSON decision carrying a register, and the character call is captured so its recency
tail can be inspected.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_EMISSION = '<speaker:1>\n<type:character_dialogue>\n"I have you. Stay with me."'


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch, character_prompts: list[str], decision: dict):
    """Route by system prompt: the planner gets ``decision``, the character gets an emission."""
    plans = iter([json.dumps(decision), json.dumps({"action": "end", "reason": "done"})])

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "scene director running one interactive-story turn" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": next(plans, '{"action": "end"}')}}]})
        if "the way it would appear in a novel" in system:
            character_prompts.append(body["messages"][1]["content"])
            return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _scene(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Smoldering Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def test_planner_register_reaches_the_character_prompt(client, storyline_id, monkeypatch):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(
        monkeypatch,
        prompts,
        {"action": "speak", "actor": 1, "register": "grave", "stakes": "he is bleeding out"},
    )
    cid, scid = _scene(client, storyline_id)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "I press down on the wound.", "directedAt": cid})
    assert resp.status_code == 200
    assert prompts, "the character was never asked to speak"
    assert "The moment is GRAVE" in prompts[0]
    assert "What is at stake right now: he is bleeding out." in prompts[0]


def test_no_register_from_the_planner_leaves_the_generic_cue(client, storyline_id, monkeypatch):
    # A planner that omits the field (or an offline fallback) must not fabricate a register.
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts, {"action": "speak", "actor": 1, "reason": "addressed"})
    cid, scid = _scene(client, storyline_id)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "I sit down.", "directedAt": cid})
    assert resp.status_code == 200
    assert prompts, "the character was never asked to speak"
    assert "The moment is" not in prompts[0]
    assert "Before you respond, read the moment" in prompts[0]


# ---- the player's pin, which reaches paths the planner never touched -------


def test_a_pinned_register_outranks_the_planner_in_the_prompt(client, storyline_id, monkeypatch):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(
        monkeypatch,
        prompts,
        {"action": "speak", "actor": 1, "register": "light", "stakes": "nothing much"},
    )
    cid, scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={
            "text": "I press down on the wound.",
            "directedAt": cid,
            "overrides": {"register": "grave"},
        },
    )

    assert resp.status_code == 200
    assert prompts, "the character was never asked to speak"
    assert "The moment is GRAVE" in prompts[0]
    assert "LIGHT" not in prompts[0]


def test_a_pin_reaches_the_puppet_path_which_carries_none_today(
    client, storyline_id, monkeypatch
):
    """The planner never runs for a puppeted beat, so before this it had no register at all."""
    _configure_llm(client)
    prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "kind": "puppet",
                                        "directive": "slam the door",
                                        "actors": [1],
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        if "the way it would appear in a novel" in system:
            prompts.append(user)
            return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})
        if "scene director running one interactive-story turn" in system:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": '{"action": "end"}'}}]}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    cid, scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Mei slams the door.", "overrides": {"register": "tense"}},
    )

    assert resp.status_code == 200
    assert prompts, "the puppeted character never spoke"
    assert any("The moment is TENSE" in p for p in prompts)


def test_the_speaker_trace_says_who_pitched_the_beat(client, storyline_id, monkeypatch):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(
        monkeypatch, prompts, {"action": "speak", "actor": 1, "register": "light"}
    )
    cid, scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={
            "text": "I press down.",
            "directedAt": cid,
            "trace": True,
            "overrides": {"register": "grave"},
        },
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    speaker = next(
        e for e in events if e["type"] == "trace" and e["step"] == "speaker"
    )

    assert speaker["data"]["register"] == "grave"
    assert speaker["data"]["registerSource"] == "player"


def test_the_trace_credits_the_planner_when_nothing_is_pinned(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts, {"action": "speak", "actor": 1, "register": "tense"})
    cid, scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "I press down.", "directedAt": cid, "trace": True},
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    speaker = next(e for e in events if e["type"] == "trace" and e["step"] == "speaker")

    assert speaker["data"]["register"] == "tense"
    assert speaker["data"]["registerSource"] == "planner"
