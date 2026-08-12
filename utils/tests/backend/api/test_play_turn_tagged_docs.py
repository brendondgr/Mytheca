"""POST /api/play/{scenarioId}/turn — the ``taggedDocIds`` round trip.

The end-to-end proof of the @-tagging path: a real ``ContextDocument`` id on the request
reaches the character prompt whole (not as a 600-character RAG snippet, and without the
conservative ``retrieval_gate`` ever firing), while a foreign world's document does not.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<type:character_dialogue>\n"
    '"Coin\'s easy."'
)

_SECRET = "Maerin keeps her sister's ring on a braided cord under her collar."


def _patch_llm(monkeypatch, prompts: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        prompts.extend(m["content"] for m in body.get("messages", []))
        return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Smoldering Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]


def _doc(client, storyline_id, name, content):
    return client.post(
        f"/api/storylines/{storyline_id}/context-docs",
        json={"name": name, "content": content},
    ).json()["id"]


def test_tagged_document_reaches_the_prompt(client, storyline_id, monkeypatch):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts)
    scenario_id = _scene(client, storyline_id)
    doc_id = _doc(client, storyline_id, "maerin.md", _SECRET)

    resp = client.post(
        f"/api/play/{scenario_id}/turn",
        json={"text": "I ask her what she is holding.", "taggedDocIds": [doc_id]},
    )

    assert resp.status_code == 200
    assert any(_SECRET in p for p in prompts)


def test_turn_without_tagged_docs_is_unchanged(client, storyline_id, monkeypatch):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts)
    scenario_id = _scene(client, storyline_id)
    _doc(client, storyline_id, "maerin.md", _SECRET)

    resp = client.post(
        f"/api/play/{scenario_id}/turn", json={"text": "I ask her what she is holding."}
    )

    assert resp.status_code == 200
    assert not any(_SECRET in p for p in prompts)
    assert not any("Reference files the player attached" in p for p in prompts)


def test_document_from_another_storyline_never_reaches_the_prompt(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts)
    scenario_id = _scene(client, storyline_id)
    other = client.post(
        "/api/storylines", json={"id": "otherworld", "title": "Otherworld", "genre": "Court"}
    ).json()["id"]
    foreign_id = _doc(client, other, "secrets.md", _SECRET)

    resp = client.post(
        f"/api/play/{scenario_id}/turn",
        json={"text": "I ask her what she is holding.", "taggedDocIds": [foreign_id]},
    )

    assert resp.status_code == 200
    assert not any(_SECRET in p for p in prompts)


def test_tagged_files_emit_a_trace_step(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, [])
    scenario_id = _scene(client, storyline_id)
    doc_id = _doc(client, storyline_id, "maerin.md", _SECRET)

    resp = client.post(
        f"/api/play/{scenario_id}/turn",
        json={"text": "I ask her what she is holding.", "taggedDocIds": [doc_id], "trace": True},
    )

    frames = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    files = [f for f in frames if f.get("step") == "files"]
    assert files, "expected a `files` trace step"
    assert files[0]["data"]["names"] == ["maerin.md"]
    assert files[0]["data"]["injected"] is True


def test_no_trace_step_when_nothing_is_tagged(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, [])
    scenario_id = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scenario_id}/turn",
        json={"text": "I ask her what she is holding.", "trace": True},
    )

    frames = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    assert not [f for f in frames if f.get("step") == "files"]
