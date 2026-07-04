"""Character authoring agent — draft, portrait prompts, starting-stat proposals.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned OpenAI-compatible completions, mirroring
``test_storyline_agent.py``. The model endpoint is configured via the Options API
on the same in-memory DB the routes use.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm, stat_guidance


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


def test_draft_grounds_in_retrieved_rag_lore(client, monkeypatch, storyline_id):
    """Utilization: an existing indexed entry is retrieved and folded into the prompt."""
    _configure_llm(client)

    from qdrant_client import QdrantClient

    from app.models import Character
    from app.rag import indexer, store
    from app.rag.embedder import HashEmbedder
    from app.rag.entries import entry_from_character

    mem = QdrantClient(":memory:")
    store.ensure_collection(mem)
    monkeypatch.setattr("app.core.qdrant.get_client", lambda: mem)
    indexer.index_entry(
        mem,
        HashEmbedder(),
        entry_from_character(
            Character(
                id="c9", storyline_id=storyline_id, name="Selka", role="Smuggler",
                background="RAG_LORE_MARKER about the tunnels beneath the harbor",
            )
        ),
    )

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_DRAFT_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/characters/draft",
        json={"seed": "a smuggler who knows the tunnels", "storylineId": storyline_id},
    )
    assert res.status_code == 200
    # The retrieved lore reached the outbound prompt — the RAG is actually used.
    assert "RAG_LORE_MARKER" in seen["body"]


def test_draft_requires_a_seed_or_docs(client):
    # An empty seed with no Draft reference docs is rejected.
    _configure_llm(client)
    res = client.post("/api/characters/draft", json={"seed": "   "})
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
        "/api/characters/draft",
        json={"seed": "   ", "docsOverview": "MARKER_CHAR_DOSSIER"},
    )
    assert res.status_code == 200
    assert "MARKER_CHAR_DOSSIER" in seen["body"]


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


_VOICE_JSON = json.dumps(
    {
        "samples": [
            {"situation": "greeted warmly", "sample": "State your business."},
            {"situation": "offered a bribe", "sample": "Coin talks. I decide what it says."},
            {"situation": "cornered", "sample": "Back off. Now."},
            {"situation": "praised", "sample": "Flattery's cheap."},
            {"situation": "extra pair over the cap", "sample": "dropped by the cap"},
        ]
    }
)


def test_voice_samples_parses_and_caps(client, monkeypatch, storyline_id):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(_VOICE_JSON)

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/characters/voice-samples",
        json={
            "name": "Fenwick",
            "speech": "clipped, wary",
            "personality": "guarded and transactional",
            "storylineId": storyline_id,
        },
    )
    assert res.status_code == 200
    samples = res.json()["samples"]
    assert len(samples) == 4  # capped at _VOICE_SAMPLES_CAP, the 5th pair dropped
    assert samples[0]["situation"] == "greeted warmly"
    assert samples[0]["sample"] == "State your business."
    # The character's voice fields are handed to the model.
    assert "clipped, wary" in seen["body"]


def test_voice_samples_empty_without_description(client):
    # No character fields at all → no LLM call, empty proposal.
    _configure_llm(client)
    res = client.post("/api/characters/voice-samples", json={})
    assert res.status_code == 200
    assert res.json()["samples"] == []


def test_voice_samples_best_effort_on_malformed(client, monkeypatch):
    # A non-JSON / malformed completion degrades to an empty list, never a 500.
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("not json at all"))
    res = client.post("/api/characters/voice-samples", json={"name": "Fenwick"})
    assert res.status_code == 200
    assert res.json()["samples"] == []


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


def test_starting_stats_prompt_includes_band_meanings(client, monkeypatch, storyline_id):
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={
            "key": "health",
            "displayName": "Health",
            "min": 0,
            "max": 100,
            "default": 100,
            "bands": [
                {
                    "min": 0,
                    "max": 20,
                    "label": "NEARLY_DEAD_MARKER",
                    "description": "BAND_DESC_MARKER",
                }
            ],
        },
    )
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(json.dumps({"proposals": [{"key": "health", "value": 10}]}))

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/characters/starting-stats",
        json={"storylineId": storyline_id, "name": "Wretch"},
    )
    assert res.status_code == 200
    # The band's label AND description are in the prompt so the model can choose a
    # coherent value.
    assert "NEARLY_DEAD_MARKER" in seen["body"]
    assert "BAND_DESC_MARKER" in seen["body"]


def test_starting_stats_prompt_includes_guidance_text(client, monkeypatch, storyline_id):
    """Guidance loaded from a real seeded .md file appears in the LLM prompt.

    Uses the actual ``stats/health.md`` file (which ships with the codebase) so
    the test stays offline — no network, no DB seed required beyond the stat row.
    """
    _configure_llm(client)

    # Clear the guidance cache so a fresh read occurs for this test.
    stat_guidance._clear_cache()

    # Create a stat definition that points at the real health guidance file.
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={
            "key": "health",
            "displayName": "Health",
            "min": 0,
            "max": 100,
            "default": 100,
            "guidance": "stats/health.md",
        },
    )

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion(json.dumps({"proposals": [{"key": "health", "value": 90}]}))

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/characters/starting-stats",
        json={"storylineId": storyline_id, "name": "Theron"},
    )
    assert res.status_code == 200
    # The guidance file content (title heading) must appear in the outbound prompt.
    assert "Health" in seen["body"]
    # The "Guidance:" prefix injected by the agent must be present.
    assert "Guidance:" in seen["body"]

    stat_guidance._clear_cache()
