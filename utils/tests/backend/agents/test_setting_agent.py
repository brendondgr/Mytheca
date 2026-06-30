"""Setting authoring agent — draft + scene-art prompts.

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


_DRAFT_JSON = json.dumps(
    {
        "name": "The Drowned Market",
        "type": "Black Market",
        "desc": "Below the tideline, where nothing is illegal.",
        "atmosphere": "Brine and tallow; lantern-light on standing water.",
        "features": "Submerged vault rows and plank walkways above the waterline.",
        "currentState": "Tide rising; the bells beginning to count it down.",
    }
)


def test_draft_setting_parses_json(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_DRAFT_JSON))
    res = client.post("/api/settings/draft", json={"seed": "A flooded smugglers' market."})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "The Drowned Market"
    assert data["type"] == "Black Market"
    assert data["atmosphere"].startswith("Brine and tallow")
    assert data["features"].startswith("Submerged vault")
    assert data["currentState"].startswith("Tide rising")


def test_draft_grounds_in_world_when_storyline_given(client, monkeypatch, storyline_id):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_DRAFT_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/settings/draft",
        json={"seed": "A market.", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # The active world's name reaches the prompt as grounding.
    assert "Embergate" in seen["body"]


def test_draft_docs_overview_reaches_prompt(client, monkeypatch):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_DRAFT_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/settings/draft",
        json={"seed": "A market.", "docsOverview": "MARKER_PLACE_GAZETTEER"},
    )
    assert res.status_code == 200
    assert "MARKER_PLACE_GAZETTEER" in seen["body"]


def test_draft_requires_a_seed_or_docs(client):
    # An empty seed with no Draft reference docs is rejected.
    _configure_llm(client)
    res = client.post("/api/settings/draft", json={"seed": "   "})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_draft_from_docs_without_a_seed(client, monkeypatch):
    # No seed, but Draft reference docs are present → draft from the docs.
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_DRAFT_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/settings/draft",
        json={"seed": "   ", "docsOverview": "MARKER_PLACE_GAZETTEER"},
    )
    assert res.status_code == 200
    assert "MARKER_PLACE_GAZETTEER" in seen["body"]


def test_draft_without_llm_is_bad_request(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/settings/draft", json={"seed": "A market."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_scene_art_prompts_returns_positive_and_negative(client, monkeypatch):
    _configure_llm(client)
    payload = json.dumps(
        {
            "positive": "fog-bound harbor at dawn, rotting jetties, cold light, "
            "watercolor, soft washes, establishing shot, no people",
            "negative": "people, figures, photorealistic, text, watermark",
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(payload))
    res = client.post(
        "/api/settings/scene-art-prompts",
        json={"name": "Embergate Harbor", "atmosphere": "Cold fog off the water."},
    )
    assert res.status_code == 200
    data = res.json()
    assert "watercolor" in data["positive"]
    assert "no people" in data["positive"]
    assert "watermark" in data["negative"]


def test_scene_art_prompts_require_a_description(client):
    _configure_llm(client)
    res = client.post("/api/settings/scene-art-prompts", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"
