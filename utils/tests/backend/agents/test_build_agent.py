"""World-build orchestrator — drafts the whole world, mock upstream.

The build makes several LLM calls (storyline draft, primer, blueprint, one per
character, one per setting). The mock transport routes each by a marker in the
system prompt, so a single handler serves the whole orchestration offline.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()

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


# Attached character/setting docs — the build creates exactly one entity per doc.
_CHAR_DOCS = [
    {"name": "maerin.md", "text": "Maerin Voss, a wary harbor smuggler."},
    {"name": "kestrel.md", "text": "A cold inquisitor who hunts heretics."},
]
_SETTING_DOCS = [
    {"name": "chapel.md", "text": "A drowned chapel beneath the tide."},
    {"name": "quay.md", "text": "A lantern-lit quay at the harbor's edge."},
]


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _route(request: httpx.Request) -> httpx.Response:
    # Engine-detection probes (GET /version, /props) — 404 so detection yields
    # UNKNOWN and no reasoning budget is injected (unchanged build behaviour).
    if request.url.path in ("/version", "/props"):
        return httpx.Response(404)
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


def test_build_injects_medium_thinking_budget(client, monkeypatch):
    """The world build runs at MEDIUM effort (512 thinking tokens) on a detected engine."""
    _configure_llm(client)
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(404)
        if request.url.path == "/props":  # detected as llama.cpp
            return httpx.Response(200, json={"total_slots": 2})
        bodies.append(json.loads(request.content.decode()))
        return _route(request)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/storylines/build",
        json={"seed": "A drowned harbor town.", "characterDocs": _CHAR_DOCS},
    )
    assert res.status_code == 200
    # Every authoring call (draft, primer, blueprint, per-character) carries the
    # llama.cpp budget key at MEDIUM = 512; none carries the vLLM key.
    assert bodies, "no chat completions captured"
    assert all(b.get("thinking_budget_tokens") == 512 for b in bodies)
    assert all("thinking_token_budget" not in b for b in bodies)


def test_build_world_assembles_full_proposal(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post(
        "/api/storylines/build",
        json={
            "seed": "A drowned harbor town.",
            "characterDocs": _CHAR_DOCS,
            "settingDocs": _SETTING_DOCS,
        },
    )
    assert res.status_code == 200
    world = res.json()

    assert world["storyline"]["title"] == "Embergate"
    assert world["storyline"]["genre"] == "Maritime Intrigue"
    assert "powers" in world["storyline"]["worldPrimer"]

    # Stat schema: keys slugged from display names; ranges valid; bands carried.
    keys = [s["key"] for s in world["stats"]]
    assert keys == ["health", "suspicion"]
    assert world["stats"][0]["bands"][0]["label"] == "Nearly dead"

    # Exactly one character per character-doc, one setting per setting-doc (2 each).
    assert [c["name"] for c in world["characters"]] == ["Maerin Voss", "Maerin Voss"]
    assert len(world["settings"]) == 2
    assert world["settings"][0]["name"] == "The Drowned Chapel"

    # Each character carries schema-default starting stats.
    starting = {s["key"]: s["value"] for s in world["characters"][0]["startingStats"]}
    assert starting == {"health": 100, "suspicion": 0}


def test_build_no_entity_docs_creates_no_cast(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # A seed but no attached character/setting docs → storyline + stats only; the
    # build does NOT invent a cast or settings.
    res = client.post("/api/storylines/build", json={"seed": "A drowned harbor town."})
    assert res.status_code == 200
    world = res.json()
    assert world["storyline"]["title"] == "Embergate"
    assert [s["key"] for s in world["stats"]] == ["health", "suspicion"]
    assert world["characters"] == []
    assert world["settings"] == []


def test_build_characters_only_when_only_character_docs(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post(
        "/api/storylines/build",
        json={"seed": "A world.", "characterDocs": _CHAR_DOCS},
    )
    assert res.status_code == 200
    world = res.json()
    assert len(world["characters"]) == 2
    assert world["settings"] == []  # no setting docs → no settings


def test_build_from_docs_only(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # Lore-only grounding (no entity docs) → storyline drafts, but no cast/settings.
    res = client.post(
        "/api/storylines/build",
        json={"docsOverview": "A bestiary of salt-wraiths and a map of the drowned coast."},
    )
    assert res.status_code == 200
    world = res.json()
    assert world["storyline"]["title"] == "Embergate"
    assert world["characters"] == []
    assert world["settings"] == []


def test_build_cast_is_uncapped(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # 9 character docs + 7 setting docs — both exceed the old 6/5 blueprint caps.
    char_docs = [{"name": f"c{i}.md", "text": f"Character {i}."} for i in range(9)]
    setting_docs = [{"name": f"s{i}.md", "text": f"Setting {i}."} for i in range(7)]
    res = client.post(
        "/api/storylines/build",
        json={"seed": "A world.", "characterDocs": char_docs, "settingDocs": setting_docs},
    )
    assert res.status_code == 200
    world = res.json()
    assert len(world["characters"]) == 9  # all of them, not capped
    assert len(world["settings"]) == 7


def test_build_from_attached_docs_only_no_seed(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # Attached docs alone are enough context (no seed, no lore) — and drive the cast.
    res = client.post(
        "/api/storylines/build",
        json={"characterDocs": _CHAR_DOCS, "settingDocs": _SETTING_DOCS},
    )
    assert res.status_code == 200
    world = res.json()
    assert len(world["characters"]) == 2
    assert len(world["settings"]) == 2


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


# ---- streaming build (NDJSON) ----------------------------------------------


def _stream_events(res) -> list[dict]:
    """Parse an ``application/x-ndjson`` body into a list of event dicts."""
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def test_build_stream_emits_event_sequence(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post(
        "/api/storylines/build/stream",
        json={
            "seed": "A drowned harbor town.",
            "characterDocs": _CHAR_DOCS,
            "settingDocs": _SETTING_DOCS,
        },
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    events = _stream_events(res)
    types = [e["type"] for e in events]

    # Ordered stages, one per-entity event per attached doc, and a terminal `done`.
    assert types[0] == "status"
    assert "meta" in types and "primer" in types and "plan" in types
    assert types.count("character") == 2  # one per character doc
    assert types.count("setting") == 2  # one per setting doc
    assert types[-1] == "done"

    meta = next(e for e in events if e["type"] == "meta")
    assert meta["title"] == "Embergate"
    plan = next(e for e in events if e["type"] == "plan")
    assert [s["key"] for s in plan["stats"]] == ["health", "suspicion"]
    # The plan's skeleton labels are the attached doc names.
    assert plan["characters"] == ["maerin.md", "kestrel.md"]

    first_char = next(e for e in events if e["type"] == "character")
    assert first_char["index"] == 0
    assert first_char["character"]["name"] == "Maerin Voss"


def test_build_stream_no_entity_docs_no_cast(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    events = _stream_events(
        client.post("/api/storylines/build/stream", json={"seed": "A world."})
    )
    types = [e["type"] for e in events]
    assert "meta" in types and "plan" in types  # storyline + stats still produced
    assert types.count("character") == 0  # nothing invented
    assert types.count("setting") == 0
    done = next(e for e in events if e["type"] == "done")
    assert done["world"]["characters"] == []
    assert done["world"]["settings"] == []


def test_build_stream_done_matches_collector(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    body = {"seed": "A harbor.", "characterDocs": _CHAR_DOCS, "settingDocs": _SETTING_DOCS}
    streamed = _stream_events(client.post("/api/storylines/build/stream", json=body))
    done = next(e for e in streamed if e["type"] == "done")
    collected = client.post("/api/storylines/build", json=body).json()
    assert done["world"] == collected


def test_build_stream_requires_context(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    res = client.post("/api/storylines/build/stream", json={})
    assert res.status_code == 400  # validated before the stream opens
    assert res.json()["error"]["code"] == "bad_request"


def test_build_stream_requires_llm_configured(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/storylines/build/stream", json={"seed": "A world."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_build_stream_emits_error_event_on_upstream_failure(client, monkeypatch):
    _configure_llm(client)

    def handler(request: httpx.Request) -> httpx.Response:
        # The very first call (storyline draft) returns junk → extract_json raises
        # mid-stream, after the 200 has opened → surfaces as an in-band error event.
        return _completion("not json at all")

    _patch_upstream(monkeypatch, handler)
    res = client.post("/api/storylines/build/stream", json={"seed": "A world."})
    assert res.status_code == 200  # the stream already opened
    events = _stream_events(res)
    assert events[-1]["type"] == "error"
    assert "JSON" in events[-1]["message"] or events[-1]["message"]
