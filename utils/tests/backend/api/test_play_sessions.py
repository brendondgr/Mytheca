"""Session review + export endpoints: list / history / close / export.

These back persistent scene saving — a scenario's play-through is reopenable with its
full history (turns, thoughts, and the graph/RAG diagnostic trace) intact — and the
Export control (JSON + Markdown). LLM is offline-mocked like ``test_play_turn``.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Coin first, favor later.</thinking>\n"
    "Mei doesn't touch the pouch.\n"
    '"Coin\'s easy."'
)


def _patch_llm(monkeypatch, content: str = _EMISSION):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scenario(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _play(client, scid, cid, text="I slide the coin pouch toward Mei."):
    resp = client.post(f"/api/play/{scid}/turn", json={"text": text, "directedAt": cid})
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    return events[0]["sessionId"]


def test_sessions_list_empty_then_reports_turn_after_play(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    assert client.get(f"/api/play/{scid}/sessions").json()["sessions"] == []

    _play(client, scid, cid, text="Hello there.")
    sessions = client.get(f"/api/play/{scid}/sessions").json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["turnCount"] == 1
    assert sessions[0]["preview"] == "Hello there."  # first player line labels the play-through
    assert sessions[0]["closedAt"] is None


def test_history_returns_events_thoughts_and_persisted_trace(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    session_id = _play(client, scid, cid)

    body = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    types = [e["type"] for e in body["events"]]
    assert "user_turn" in types  # the player line is part of the record
    assert "internal_thought" in types  # the hidden thought was persisted
    assert "character_prose" in types
    # The graph/RAG diagnostics survive even though trace was never requested on the wire.
    steps = {t["step"] for t in body["traces"]}
    assert {"turn", "lore", "commit"} <= steps
    assert body["session"]["turnCount"] == 1


def test_close_marks_closed(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    session_id = _play(client, scid, cid)
    closed = client.post(f"/api/play/{scid}/sessions/{session_id}/close").json()
    assert closed["closedAt"] is not None
    # Idempotent.
    assert client.post(f"/api/play/{scid}/sessions/{session_id}/close").status_code == 200


def test_export_json_is_structured_by_turn(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    session_id = _play(client, scid, cid)
    resp = client.get(f"/api/play/{scid}/sessions/{session_id}/export?format=json")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    doc = json.loads(resp.text)
    assert doc["turnCount"] == 1
    turn = doc["turns"][0]
    assert turn["player"]["text"].startswith("I slide the coin")
    assert turn["player"]["directedAt"] == "Mei"  # id resolved to name
    kinds = {b["type"] for b in turn["beats"]}
    assert {"internal_thought", "character_prose"} <= kinds
    # Graph + RAG activity is present in the exported trace.
    assert {s["step"] for s in turn["trace"]} >= {"lore", "commit"}


def test_export_markdown_is_human_readable(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    session_id = _play(client, scid, cid)
    resp = client.get(f"/api/play/{scid}/sessions/{session_id}/export?format=md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    md = resp.text
    assert "# Standoff — Conversation Export" in md
    assert "## Turn 1" in md
    assert "**You** (to Mei): I slide the coin" in md
    assert "*Mei thinks:*" in md  # the private thought is inlined
    assert "Diagnostics" in md  # graph/RAG steps rendered


def test_export_rejects_unknown_format(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    session_id = _play(client, scid, cid)
    assert client.get(f"/api/play/{scid}/sessions/{session_id}/export?format=xml").status_code == 422


def test_unknown_scenario_and_session_404(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    assert client.get("/api/play/nope/sessions").status_code == 404
    assert client.get(f"/api/play/{scid}/sessions/ps_missing").status_code == 404
    session_id = _play(client, scid, cid)
    # A session that belongs to a different scenario is a 400.
    _, other = _scenario(client, storyline_id)
    assert client.get(f"/api/play/{other}/sessions/{session_id}").status_code == 400
