"""World-build orchestrator — drafts the whole world, mock upstream.

The build makes several LLM calls (storyline draft, primer, blueprint, one per
character, one per setting). The mock transport routes each by a marker in the
system prompt, so a single handler serves the whole orchestration offline.
"""

from __future__ import annotations

import json
import re

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
_VOICE = json.dumps(
    {
        "samples": [
            {"situation": "questioned", "sample": "Ask again. Slower."},
            {"situation": "threatened", "sample": "Try it."},
        ]
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


def _extract_payload(body: str) -> str:
    """Deterministic entity-extraction reply keyed off the document content.

    The build now mines every attached doc for its distinct characters/settings; the
    mock returns a roster shaped by keywords so a single 'roster'/'mixed' doc yields
    several entities, the canonical maerin/kestrel/chapel/quay docs each yield their
    one subject, and generic 'Character N'/'Setting N' docs yield a uniquely-named
    entity (so cross-doc de-dup and counts are exercised)."""
    content = json.loads(body)["messages"][1]["content"].lower()
    chars: list[dict] = []
    settings: list[dict] = []
    if "roster" in content:  # one doc → several characters
        chars = [
            {"name": "Aldous Finch", "source": "A grizzled harbor captain."},
            {"name": "Wynn Calder", "source": "A nimble young lookout."},
            {"name": "Sera Dunne", "source": "A cunning quartermaster."},
        ]
    elif "mixed" in content:  # one doc → a character AND a setting
        chars = [{"name": "Bram Hollow", "source": "A taciturn ferryman."}]
        settings = [{"name": "The Reed Crossing", "source": "A misted tidal ford."}]
    elif "maerin" in content or "smuggler" in content:
        chars = [{"name": "Maerin Voss", "source": "A wary harbor smuggler."}]
    elif "inquisitor" in content:
        chars = [{"name": "Inquisitor Kestrel", "source": "A cold heretic-hunter."}]
    elif "chapel" in content:
        settings = [{"name": "The Drowned Chapel", "source": "A sunken shrine."}]
    elif "quay" in content:
        settings = [{"name": "The Lantern Quay", "source": "A lantern-lit pier."}]
    else:  # generic "character N" / "setting N" docs → uniquely-named entities
        mc = re.search(r"character (\d+)", content)
        ms = re.search(r"setting (\d+)", content)
        if mc:
            chars = [{"name": f"Char {mc.group(1)}", "source": content}]
        if ms:
            settings = [{"name": f"Place {ms.group(1)}", "source": content}]
    return json.dumps({"characters": chars, "settings": settings})


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
    if "entity-extraction assistant" in body:
        return _completion(_extract_payload(body))
    if "character-voice assistant" in body:
        return _completion(_VOICE)
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

    # Voice & tone samples are generated (before stats) and ride the proposal.
    samples = world["characters"][0]["voiceSamples"]
    assert [s["situation"] for s in samples] == ["questioned", "threatened"]
    assert samples[0]["sample"] == "Ask again. Slower."


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


def test_build_splits_a_multi_character_doc(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # A SINGLE document describing several characters must yield one card per person
    # (the bug: these used to be dropped / collapsed into one).
    res = client.post(
        "/api/storylines/build",
        json={
            "seed": "A harbor.",
            "characterDocs": [{"name": "crew.md", "text": "The ship's roster of three sailors."}],
        },
    )
    assert res.status_code == 200
    world = res.json()
    assert len(world["characters"]) == 3  # three distinct subjects from one doc
    starting = {s["key"]: s["value"] for s in world["characters"][0]["startingStats"]}
    assert starting == {"health": 100, "suspicion": 0}


def test_build_mines_other_bucket_doc_for_characters_and_settings(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # An 'other'-bucket doc (multi-subject / mixed) is now mined too — it yields both
    # a character and a setting instead of vanishing into lore.
    events = _stream_events(
        client.post(
            "/api/storylines/build/stream",
            json={"otherDocs": [{"name": "scene.md", "text": "A mixed scene at a crossing."}]},
        )
    )
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["characters"] == ["Bram Hollow"]
    assert plan["settings"] == ["The Reed Crossing"]
    done = next(e for e in events if e["type"] == "done")
    assert len(done["world"]["characters"]) == 1
    assert len(done["world"]["settings"]) == 1


def test_build_dedups_subjects_across_docs(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    # The same character named in two docs collapses to one card (folded-name dedup).
    res = client.post(
        "/api/storylines/build",
        json={
            "seed": "A harbor.",
            "characterDocs": [
                {"name": "a.md", "text": "Maerin the smuggler."},
                {"name": "b.md", "text": "More notes on Maerin Voss, smuggler."},
            ],
        },
    )
    assert res.status_code == 200
    assert len(res.json()["characters"]) == 1


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
    # The plan's skeleton labels are the EXTRACTED subject names (not doc filenames).
    assert plan["characters"] == ["Maerin Voss", "Inquisitor Kestrel"]
    assert plan["settings"] == ["The Drowned Chapel", "The Lantern Quay"]

    # Drafting is concurrent, so character events may arrive out of order — the page
    # places each by its `index`. Assert both slots are present (order-independent).
    char_events = {e["index"]: e["character"]["name"] for e in events if e["type"] == "character"}
    assert set(char_events) == {0, 1}
    assert all(name == "Maerin Voss" for name in char_events.values())


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


# ---- parallel drafting (configurable authoringConcurrency) -------------------


def test_build_concurrency_one_drafts_sequentially_in_order(client, monkeypatch):
    _configure_llm(client)
    client.patch("/api/options/llm", json={"authoringConcurrency": 1})
    _patch_upstream(monkeypatch)
    events = _stream_events(
        client.post(
            "/api/storylines/build/stream",
            json={"seed": "A harbor.", "characterDocs": _CHAR_DOCS, "settingDocs": _SETTING_DOCS},
        )
    )
    # With concurrency=1 the pool runs inline in order → events stream 0, 1, …
    char_indices = [e["index"] for e in events if e["type"] == "character"]
    setting_indices = [e["index"] for e in events if e["type"] == "setting"]
    assert char_indices == [0, 1]
    assert setting_indices == [0, 1]


def test_build_tolerates_out_of_order_completion(client, monkeypatch):
    # Simulate parallel drafts finishing in reverse: the build must still place each
    # by index and assemble the final world correctly (drops nothing).
    from app.agents import build_agent

    real = build_agent.concurrency.imap_unordered

    def reversed_imap(thunks, **kw):
        yield from reversed(list(real(thunks, max_workers=1)))

    monkeypatch.setattr(build_agent.concurrency, "imap_unordered", reversed_imap)
    _configure_llm(client)
    _patch_upstream(monkeypatch)
    events = _stream_events(
        client.post(
            "/api/storylines/build/stream",
            json={"seed": "A harbor.", "characterDocs": _CHAR_DOCS, "settingDocs": _SETTING_DOCS},
        )
    )
    # Character events arrive newest-index-first, but both slots land + done is whole.
    char_indices = [e["index"] for e in events if e["type"] == "character"]
    assert char_indices == [1, 0]
    done = next(e for e in events if e["type"] == "done")
    assert len(done["world"]["characters"]) == 2
    assert len(done["world"]["settings"]) == 2


def test_build_skips_a_failed_per_entity_draft(client, monkeypatch):
    # One character draft returns junk → that entity is dropped (best-effort), the
    # rest of the world still builds and the stream still ends with `done`.
    _configure_llm(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/version", "/props"):
            return httpx.Response(404)
        body = request.content.decode()
        # Fail only the Kestrel character draft (its focused source brief).
        if "character-creation assistant" in body and "heretic-hunter" in body:
            return _completion("not json")
        return _route(request)

    _patch_upstream(monkeypatch, handler)
    events = _stream_events(
        client.post(
            "/api/storylines/build/stream",
            json={"seed": "A harbor.", "characterDocs": _CHAR_DOCS},
        )
    )
    assert events[-1]["type"] == "done"  # no error — the failure was isolated
    # Two characters were extracted; one draft failed → one card survives, one event.
    assert sum(1 for e in events if e["type"] == "character") == 1
    done = next(e for e in events if e["type"] == "done")
    assert len(done["world"]["characters"]) == 1
