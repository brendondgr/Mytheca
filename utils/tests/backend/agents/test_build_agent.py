"""World-build orchestrator — drafts the whole world, mock upstream.

The build makes several LLM calls (storyline draft, primer, blueprint, one per
character, one per setting). The mock transport routes each by a marker in the
system prompt, so a single handler serves the whole orchestration offline.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_STORYLINE = json.dumps(
    {
        "title": "Embergate",
        "genre": "Maritime Intrigue",
        "tagline": "Every secret has a price.",
        "premise": "A drowned coast.\n\nThree powers circle the port.",
    }
)
_BLUEPRINT = json.dumps(
    {
        "stats": [
            {
                "displayName": "Health",
                "description": "Body.",
                "min": 0,
                "max": 100,
                "default": 100,
                "bands": [
                    {"min": 0, "max": 20, "label": "Nearly dead"},
                    {"min": 81, "max": 100, "label": "Hale"},
                ],
            },
            {"displayName": "Suspicion", "description": "Heat.", "min": 0, "max": 100, "default": 0},
        ],
        "characters": ["A wary smuggler.", "A cold inquisitor."],
        "settings": ["A drowned chapel.", "A lantern-lit quay."],
    }
)
_CHARACTER = json.dumps(
    {
        "name": "Maerin Voss",
        "role": "Smuggler",
        "traits": "Wary · Sharp",
        "speech": "Clipped.",
        "goal": "Get out.",
        "secret": "An informant.",
        "appearance": "Weathered.",
        "background": "Dockborn.",
        "personality": "Guarded.",
        "color": "#3A5A78",
    }
)
_SETTING = json.dumps(
    {
        "name": "The Drowned Chapel",
        "type": "Sacred",
        "desc": "Below the tide.",
        "atmosphere": "Brine.",
        "features": "An altar.",
        "currentState": "Tide rising.",
    }
)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _route(request: httpx.Request) -> httpx.Response:
    body = request.content.decode()
    if "draft its library metadata" in body:
        return _completion(_STORYLINE)
    if "writing a World Primer" in body:
        return _completion("Play it grim. Three powers rule the port.")
    if "world-architect" in body:
        return _completion(_BLUEPRINT)
    if "character-creation assistant" in body:
        return _completion(_CHARACTER)
    if "setting-creation assistant" in body:
        return _completion(_SETTING)
    raise AssertionError(f"unexpected upstream call: {body[:200]}")


def _patch_upstream(monkeypatch, handler=_route):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def test_build_world_assembles_full_proposal(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post("/api/storylines/build", json={"seed": "A drowned harbor town."})
    assert res.status_code == 200
    world = res.json()

    assert world["storyline"]["title"] == "Embergate"
    assert world["storyline"]["genre"] == "Maritime Intrigue"
    assert "powers" in world["storyline"]["worldPrimer"]

    # Stat schema: keys slugged from display names; ranges valid; bands carried.
    keys = [s["key"] for s in world["stats"]]
    assert keys == ["health", "suspicion"]
    assert world["stats"][0]["bands"][0]["label"] == "Nearly dead"

    # Cast + settings drafted from the blueprint concepts (2 each here).
    assert [c["name"] for c in world["characters"]] == ["Maerin Voss", "Maerin Voss"]
    assert len(world["settings"]) == 2
    assert world["settings"][0]["name"] == "The Drowned Chapel"

    # Each character carries schema-default starting stats.
    starting = {s["key"]: s["value"] for s in world["characters"][0]["startingStats"]}
    assert starting == {"health": 100, "suspicion": 0}


def test_build_caps_counts(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post(
        "/api/storylines/build",
        json={"seed": "A world.", "maxCharacters": 1, "maxSettings": 1},
    )
    assert res.status_code == 200
    world = res.json()
    assert len(world["characters"]) == 1
    assert len(world["settings"]) == 1


def test_build_from_docs_only(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # No seed — the dropped-doc text carries the substance.
    res = client.post(
        "/api/storylines/build",
        json={"docsOverview": "A bestiary of salt-wraiths and a map of the drowned coast."},
    )
    assert res.status_code == 200
    assert res.json()["storyline"]["title"] == "Embergate"


def test_build_requires_seed_or_docs(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post("/api/storylines/build", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_build_requires_llm_configured(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/storylines/build", json={"seed": "A world."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"
