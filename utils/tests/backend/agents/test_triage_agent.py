"""Triage agent — document classification, mock upstream.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned completions, exactly like
``test_storyline_agent.py``.
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


def test_triage_classifies_each_doc(client, monkeypatch):
    _configure_llm(client)
    reply = json.dumps(
        {
            "items": [
                {"name": "maerin.md", "category": "character", "includeDraft": False, "includeRag": True},
                {"name": "tavern.md", "category": "setting", "includeDraft": False, "includeRag": True},
                {"name": "history.md", "category": "other", "includeDraft": True, "includeRag": True},
            ]
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(reply))
    res = client.post(
        "/api/storylines/triage",
        json={
            "docs": [
                {"name": "maerin.md", "text": "Maerin Voss, a harbor smuggler."},
                {"name": "tavern.md", "text": "The Saltworn Tavern, lamplit and low."},
                {"name": "history.md", "text": "Three powers rose from the drowned coast."},
            ]
        },
    )
    assert res.status_code == 200
    items = {i["name"]: i for i in res.json()["items"]}
    assert items["maerin.md"]["category"] == "character"
    assert items["tavern.md"]["category"] == "setting"
    assert items["history.md"]["category"] == "other"
    # World history is the one doc that should ground drafting.
    assert items["history.md"]["includeDraft"] is True


def test_triage_multi_character_doc_goes_to_other(client, monkeypatch):
    _configure_llm(client)
    reply = json.dumps(
        {"items": [{"name": "cast.md", "category": "other", "includeDraft": False, "includeRag": True}]}
    )
    _patch_upstream(monkeypatch, lambda req: _completion(reply))
    res = client.post(
        "/api/storylines/triage",
        json={"docs": [{"name": "cast.md", "text": "Maerin, Kael, and Brisa each want the ledger."}]},
    )
    assert res.json()["items"][0]["category"] == "other"


def test_triage_empty_docs_skips_llm(client, monkeypatch):
    _configure_llm(client)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("LLM should not be called for empty docs")

    _patch_upstream(monkeypatch, handler)
    res = client.post("/api/storylines/triage", json={"docs": []})
    assert res.status_code == 200
    assert res.json()["items"] == []


def test_triage_skips_blank_docs(client, monkeypatch):
    _configure_llm(client)
    # Only the non-blank doc reaches the model and the result.
    reply = json.dumps({"items": [{"name": "real.md", "category": "setting"}]})
    _patch_upstream(monkeypatch, lambda req: _completion(reply))
    res = client.post(
        "/api/storylines/triage",
        json={"docs": [{"name": "blank.md", "text": "   "}, {"name": "real.md", "text": "A place."}]},
    )
    names = [i["name"] for i in res.json()["items"]]
    assert names == ["real.md"]


def test_triage_falls_back_for_omitted_or_malformed(client, monkeypatch):
    _configure_llm(client)
    # The model returns nothing usable → every doc defaults to Other / RAG-on.
    _patch_upstream(monkeypatch, lambda req: _completion("Sorry, I cannot."))
    res = client.post(
        "/api/storylines/triage",
        json={"docs": [{"name": "a.md", "text": "Some lore."}]},
    )
    assert res.status_code == 502  # malformed JSON → upstream_error (no items to salvage)
    assert res.json()["error"]["code"] == "upstream_error"


def test_triage_fills_missing_doc_with_fallback(client, monkeypatch):
    _configure_llm(client)
    # Model classifies one doc but omits the other → the omitted one falls back.
    reply = json.dumps({"items": [{"name": "a.md", "category": "character"}]})
    _patch_upstream(monkeypatch, lambda req: _completion(reply))
    res = client.post(
        "/api/storylines/triage",
        json={"docs": [{"name": "a.md", "text": "A person."}, {"name": "b.md", "text": "A place."}]},
    )
    items = {i["name"]: i for i in res.json()["items"]}
    assert items["a.md"]["category"] == "character"
    assert items["b.md"]["category"] == "other"  # fallback
    assert items["b.md"]["includeRag"] is True


def test_triage_requires_llm_configured(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post(
        "/api/storylines/triage", json={"docs": [{"name": "a.md", "text": "x"}]}
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_request"
