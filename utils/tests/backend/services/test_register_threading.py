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
        if "You voice exactly ONE character" in system:
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
