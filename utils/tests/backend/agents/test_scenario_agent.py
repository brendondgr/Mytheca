"""Scenario authoring agent — draft with roster-grounded name→id resolution.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned OpenAI-compatible completions, mirroring
``test_character_agent.py``. The model endpoint is configured via the Options API
on the same in-memory DB the routes use.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _add_character(client, storyline_id: str, name: str, **fields) -> str:
    return client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": name, **fields}
    ).json()["id"]


def _add_setting(client, storyline_id: str, name: str, **fields) -> str:
    return client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": name, **fields}
    ).json()["id"]


def _draft_json(cast, setting, **over) -> str:
    payload = {
        "title": "The Salt Ledger",
        "genre": "Intrigue",
        "tone": "Tension · rising",
        "goal": "Keep the ledger out of the wrong hands.",
        "opening": "Lamplight gutters over the wet dock as the meeting begins.",
        "cast": cast,
        "setting": setting,
    }
    payload.update(over)
    return json.dumps(payload)


def test_draft_requires_a_seed(client):
    _configure_llm(client)
    res = client.post("/api/scenarios/draft", json={"seed": "   "})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_draft_without_llm_is_bad_request(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/scenarios/draft", json={"seed": "A tense negotiation."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_draft_grounds_in_world_when_storyline_given(client, monkeypatch, storyline_id):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_draft_json([], ""))

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/scenarios/draft",
        json={"seed": "A tense negotiation.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # The active world's name reaches the prompt as grounding.
    assert "Embergate" in seen["body"]


def test_draft_roster_reaches_prompt(client, monkeypatch, storyline_id):
    _configure_llm(client)
    _add_character(client, storyline_id, "MARKER_CAST_NAME")
    _add_setting(client, storyline_id, "MARKER_PLACE_NAME")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_draft_json(["MARKER_CAST_NAME"], "MARKER_PLACE_NAME"))

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/scenarios/draft",
        json={"seed": "A tense negotiation.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # The real roster (cast + setting names) is offered to the model.
    assert "MARKER_CAST_NAME" in seen["body"]
    assert "MARKER_PLACE_NAME" in seen["body"]


def test_draft_resolves_cast_names_to_ids(client, monkeypatch, storyline_id):
    _configure_llm(client)
    maerin = _add_character(client, storyline_id, "Maerin")
    doran = _add_character(client, storyline_id, "Doran Hale")
    harbor = _add_setting(client, storyline_id, "The Harbor")

    # Model returns names (one with different casing/whitespace) — all should resolve.
    _patch_upstream(
        monkeypatch,
        lambda req: _completion(_draft_json(["maerin", "  Doran   Hale "], "the harbor")),
    )
    res = client.post(
        "/api/scenarios/draft",
        json={"seed": "A tense negotiation.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["castIds"] == [maerin, doran]
    assert data["settingId"] == harbor


def test_draft_drops_unknown_cast_name(client, monkeypatch, storyline_id):
    _configure_llm(client)
    maerin = _add_character(client, storyline_id, "Maerin")
    _add_setting(client, storyline_id, "The Harbor")

    _patch_upstream(
        monkeypatch,
        lambda req: _completion(_draft_json(["Maerin", "Nobody McGhost"], "The Harbor")),
    )
    res = client.post(
        "/api/scenarios/draft",
        json={"seed": "A tense negotiation.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # The invented name is dropped — only the real id survives.
    assert res.json()["castIds"] == [maerin]


def test_draft_unknown_setting_resolves_to_empty(client, monkeypatch, storyline_id):
    _configure_llm(client)
    _add_character(client, storyline_id, "Maerin")
    _add_setting(client, storyline_id, "The Harbor")

    _patch_upstream(
        monkeypatch,
        lambda req: _completion(_draft_json(["Maerin"], "A Place That Does Not Exist")),
    )
    res = client.post(
        "/api/scenarios/draft",
        json={"seed": "A tense negotiation.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # A bad setting reference falls back to "" (the soft-reference contract).
    assert res.json()["settingId"] == ""
