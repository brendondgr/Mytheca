"""Storyline authoring agent — draft + World Primer generation, mock upstream.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned OpenAI-compatible completions. The model
endpoint is configured via the Options API first (same in-memory DB the routes
use), mirroring ``utils/tests/backend/api/test_llm.py``.
"""

from __future__ import annotations

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


def test_draft_storyline_parses_fenced_json(client, monkeypatch):
    _configure_llm(client)
    fenced = (
        '```json\n{"title": "Embergate", "genre": "Maritime Intrigue", '
        '"tagline": "Every secret has a price.", '
        '"premise": "A drowned coast.\\n\\nThree powers circle the port."}\n```'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).endswith("/chat/completions")
        return _completion(fenced)

    _patch_upstream(monkeypatch, handler)
    res = client.post("/api/storylines/draft", json={"seed": "A drowned harbor town."})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Embergate"
    assert data["genre"] == "Maritime Intrigue"
    assert data["tagline"] == "Every secret has a price."
    assert "\n\n" in data["premise"]


def test_generate_primer_returns_prose(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("Play it grim.\n\nThree powers rule Embergate."))
    res = client.post("/api/storylines/primer", json={"premise": "A drowned harbor town."})
    assert res.status_code == 200
    assert "Three powers" in res.json()["worldPrimer"]


def test_primer_accepts_seed_only(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("A terse primer."))
    res = client.post("/api/storylines/primer", json={"seed": "A drowned harbor town."})
    assert res.status_code == 200
    assert res.json()["worldPrimer"] == "A terse primer."


def test_docs_overview_reaches_the_prompt(client, monkeypatch):
    _configure_llm(client)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return _completion("ok primer")

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/storylines/primer",
        json={"premise": "A world.", "docsOverview": "MARKER_BESTIARY_NOTE"},
    )
    assert res.status_code == 200
    assert "MARKER_BESTIARY_NOTE" in seen["body"]


def test_draft_malformed_json_maps_to_upstream_error(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("Sorry, I can't do that."))
    res = client.post("/api/storylines/draft", json={"seed": "x"})
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "upstream_error"


def test_empty_completion_maps_to_upstream_error(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("   "))
    res = client.post("/api/storylines/primer", json={"premise": "A world."})
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "upstream_error"


def test_draft_without_llm_configured_is_bad_request(client):
    # Clear any seeded default endpoint → unconfigured (no network involved).
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post("/api/storylines/draft", json={"seed": "A world."})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_draft_requires_a_seed(client):
    _configure_llm(client)
    res = client.post("/api/storylines/draft", json={"seed": "   "})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"


def test_primer_requires_premise_or_seed(client):
    _configure_llm(client)
    res = client.post("/api/storylines/primer", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"
