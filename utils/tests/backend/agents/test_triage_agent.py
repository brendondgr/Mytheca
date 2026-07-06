"""Triage agent — document classification, mock upstream.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned completions, exactly like
``test_storyline_agent.py``.
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
                {"name": "maerin.md", "category": "character", "includeDraft": False,
                 "includeRag": True, "includeExtract": True},
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
    # includeExtract is coerced from the reply; omitting it defaults to False (opt-in).
    assert items["maerin.md"]["includeExtract"] is True
    assert items["tavern.md"]["includeExtract"] is False
    assert items["history.md"]["includeExtract"] is False


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


def test_triage_injects_low_thinking_budget(client, monkeypatch):
    """Triage runs at LOW effort (256 thinking tokens) on a detected engine."""
    _configure_llm(client)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":  # detected as vLLM
            return httpx.Response(200, json={"version": "0.21.0"})
        if request.url.path == "/props":
            return httpx.Response(404)
        captured.update(json.loads(request.content.decode()))
        return _completion(json.dumps({"items": [{"name": "a.md", "category": "other"}]}))

    _patch_upstream(monkeypatch, handler)
    res = client.post("/api/storylines/triage", json={"docs": [{"name": "a.md", "text": "Lore."}]})
    assert res.status_code == 200
    assert captured["thinking_token_budget"] == 256  # LOW


# ---- streaming (per-file) triage -------------------------------------------


def _stream_events(res) -> list[dict]:
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def _per_doc_router(request: httpx.Request) -> httpx.Response:
    """Classify one doc per call, by the name embedded in the user message."""
    body = request.content.decode()
    if "maerin.md" in body:
        return _completion(json.dumps({"category": "character", "includeRag": True}))
    if "tavern.md" in body:
        return _completion(json.dumps({"category": "setting", "includeRag": True}))
    return _completion(json.dumps({"category": "other", "includeDraft": True, "includeRag": True}))


def test_triage_stream_emits_per_file_events(client, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, _per_doc_router)
    res = client.post(
        "/api/storylines/triage/stream",
        json={
            "docs": [
                {"name": "maerin.md", "text": "Maerin Voss, a harbor smuggler."},
                {"name": "tavern.md", "text": "The Saltworn Tavern, lamplit and low."},
                {"name": "history.md", "text": "Three powers rose from the drowned coast."},
            ]
        },
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    events = _stream_events(res)
    # One status + one item per file, terminal done; statuses carry index/total.
    assert [e["type"] for e in events] == [
        "status", "item", "status", "item", "status", "item", "done",
    ]
    statuses = [e for e in events if e["type"] == "status"]
    assert statuses[0] == {"type": "status", "name": "maerin.md", "index": 0, "total": 3}
    items = {e["item"]["name"]: e["item"] for e in events if e["type"] == "item"}
    assert items["maerin.md"]["category"] == "character"
    assert items["tavern.md"]["category"] == "setting"
    assert items["history.md"]["category"] == "other"
    assert items["history.md"]["includeDraft"] is True


def test_triage_stream_falls_back_per_doc_on_bad_json(client, monkeypatch):
    _configure_llm(client)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "good.md" in body:
            return _completion(json.dumps({"category": "setting"}))
        return _completion("not json")  # bad.md → per-doc fallback, not an abort

    _patch_upstream(monkeypatch, handler)
    res = client.post(
        "/api/storylines/triage/stream",
        json={"docs": [{"name": "good.md", "text": "A place."}, {"name": "bad.md", "text": "x"}]},
    )
    events = _stream_events(res)
    items = {e["item"]["name"]: e["item"] for e in events if e["type"] == "item"}
    assert items["good.md"]["category"] == "setting"
    assert items["bad.md"]["category"] == "other"  # fallback
    assert items["bad.md"]["includeRag"] is True
    assert events[-1]["type"] == "done"


def test_triage_stream_empty_docs_skips_llm(client):
    # No configured LLM and no real docs → straight to `done`, no upstream call.
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post(
        "/api/storylines/triage/stream",
        json={"docs": [{"name": "blank.md", "text": "   "}]},
    )
    assert res.status_code == 200
    assert _stream_events(res) == [{"type": "done"}]


def test_triage_stream_requires_llm_configured(client):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post(
        "/api/storylines/triage/stream", json={"docs": [{"name": "a.md", "text": "x"}]}
    )
    assert res.status_code == 400  # validated before the stream opens
    assert res.json()["error"]["code"] == "bad_request"
