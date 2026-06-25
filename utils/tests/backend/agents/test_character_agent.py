"""Character authoring agent — draft, portrait prompts, starting-stat proposals.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned OpenAI-compatible completions, mirroring
``test_storyline_agent.py``. The model endpoint is configured via the Options API
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
        "name": "Captain Doran Hale",
        "role": "Lawful Blocker",
        "traits": "Dutiful · Rigid · Honourable",
        "speech": "Formal and terse.",
        "goal": "Restore order to a rotting harbor.",
        "secret": "His brother runs the black market.",
        "appearance": "Weathered, broad-shouldered, grey at the temples.",
        "background": "Rose through the Tidewatch by the book.",
        "personality": "Stern, fair, quietly weary.",
        "color": "#3A5A78",
    }
)


def test_draft_character_parses_json(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_DRAFT_JSON))
    res = client.post("/api/characters/draft", json={"seed": "A by-the-book harbor captain."})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Captain Doran Hale"
    assert data["appearance"].startswith("Weathered")
    assert data["background"].startswith("Rose through")
    assert data["personality"].startswith("Stern")
    assert data["color"] == "#3A5A78"


def test_draft_grounds_in_world_when_storyline_given(client, monkeypatch, storyline_id):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_DRAFT_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/characters/draft",
        json={"seed": "A captain.", "storylineId": storyline_id},
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
        "/api/characters/draft",
        json={"seed": "A captain.", "docsOverview": "MARKER_CHAR_DOSSIER"},
    )
    assert res.status_code == 200
    assert "MARKER_CHAR_DOSSIER" in seen["body"]


def test_draft_requires_a_seed(client):
    _configure_llm(client)
    res = client.post("/api/characters/draft", json={"seed": "   "})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_draft_without_llm_is_bad_request(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/characters/draft", json={"seed": "A captain."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_portrait_prompts_returns_positive_and_negative(client, monkeypatch):
    _configure_llm(client)
    payload = json.dumps(
        {
            "positive": "young orc warrior, green skin, braided hair, leather armor, "
            "fierce expression, watercolor portrait, soft washes",
            "negative": "photorealistic, extra limbs, blurry, text, watermark",
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(payload))
    res = client.post(
        "/api/characters/portrait-prompts",
        json={"name": "Grosh", "appearance": "A young orc warrior", "species": "orc"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "orc" in data["positive"]
    assert "watercolor portrait" in data["positive"]
    assert "watermark" in data["negative"]


def test_portrait_prompts_require_a_description(client):
    _configure_llm(client)
    res = client.post("/api/characters/portrait-prompts", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_starting_stats_empty_without_definitions(client, storyline_id):
    # No stats defined on this world and no LLM configured: returns [] with no call.
    res = client.post(
        "/api/characters/starting-stats",
        json={"storylineId": storyline_id, "name": "Grimm"},
    )
    assert res.status_code == 200
    assert res.json()["proposals"] == []


def test_starting_stats_keyed_clamped_and_completed(client, monkeypatch, storyline_id):
    _configure_llm(client)
    for stat in (
        {"key": "health", "displayName": "Health", "min": 0, "max": 100, "default": 100},
        {"key": "trust", "displayName": "Trust", "min": -5, "max": 5, "default": 0},
        {"key": "patience", "displayName": "Patience", "min": 0, "max": 10, "default": 5},
    ):
        client.post(f"/api/storylines/{storyline_id}/stats", json=stat)

    proposals = json.dumps(
        {
            "proposals": [
                {"key": "health", "value": 999, "rationale": "hardy"},  # over max → clamp
                {"key": "trust", "value": -3, "rationale": "wary"},  # in range
                {"key": "bogus", "value": 5},  # unknown → dropped
                # 'patience' omitted → filled with its default
            ]
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(proposals))
    res = client.post(
        "/api/characters/starting-stats",
        json={"storylineId": storyline_id, "name": "Grimm", "traits": "Brutal · Brief"},
    )
    assert res.status_code == 200
    by_key = {p["key"]: p for p in res.json()["proposals"]}
    assert "bogus" not in by_key
    assert by_key["health"]["value"] == 100  # clamped to max
    assert by_key["health"]["displayName"] == "Health"
    assert by_key["trust"]["value"] == -3
    assert by_key["patience"]["value"] == 5  # default fill for the skipped stat
