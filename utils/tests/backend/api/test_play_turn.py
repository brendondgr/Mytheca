"""POST /api/play/{scenarioId}/turn — POV generation + delta-streamed transport.

LLM is offline-mocked (httpx.MockTransport returning a thin-tag emission), mirroring
the agent tests. Visible dialogue delta-streams (same id + seq, incremental text,
``done`` flag); the client reconstructs by id.
"""

from __future__ import annotations

import json
from collections import defaultdict

import httpx

from app.events import story_event_adapter
from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<type:character_action>\n"
    "Mei doesn't touch the pouch. Her eyes flick once to Kira at the bar, then back.\n"
    "<type:character_dialogue>\n"
    '"Coin\'s easy. It\'s what comes after the coin I don\'t trust."'
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


def _refs(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Smoldering Hearth"}
    ).json()["id"]
    return cid, sid


def _scenario(client, storyline_id, cast, setting):
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": cast, "settingId": setting},
    ).json()["id"]


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _by_id(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        grouped[e["id"]].append(e)
    return grouped


def test_turn_streams_action_and_dialogue(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "I slide the coin pouch toward Mei.", "directedAt": cid},
    )
    assert resp.status_code == 200
    events = _stream(resp)
    types = {e["type"] for e in events}
    assert "character_action" in types and "character_dialogue" in types
    action = next(e for e in events if e["type"] == "character_action")
    assert action["data"]["characterId"] == cid
    assert "doesn't touch the pouch" in action["data"]["text"]


def test_dialogue_delta_chunks_accumulate_to_full_line(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    dialogue_chunks = [e for e in events if e["type"] == "character_dialogue"]
    assert len(dialogue_chunks) > 1  # actually delta-streamed in pieces
    # all chunks share one id + seq; only the final chunk is done.
    assert len({e["id"] for e in dialogue_chunks}) == 1
    assert len({e["seq"] for e in dialogue_chunks}) == 1
    assert [e["data"]["done"] for e in dialogue_chunks] == [False] * (len(dialogue_chunks) - 1) + [True]
    reconstructed = "".join(e["data"]["text"] for e in dialogue_chunks)
    assert reconstructed == '"Coin\'s easy. It\'s what comes after the coin I don\'t trust."'


def test_every_streamed_line_validates(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    for e in _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})):
        story_event_adapter.validate_python(e)


def test_seq_is_monotonic_and_per_event_unique(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)  # non-decreasing (chunks of one event share a seq)
    # distinct logical events (by id) have distinct seqs
    id_seq = {e["id"]: e["seq"] for e in events}
    assert len(set(id_seq.values())) == len(id_seq)
    assert min(seqs) >= 1  # seq 0 is the persisted user_turn (not streamed)


def test_session_resumes_and_seq_continues(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    first = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "one", "directedAt": cid}))
    session_id = first[0]["sessionId"]
    second = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "two", "directedAt": cid, "sessionId": session_id},
        )
    )
    assert all(e["sessionId"] == session_id for e in second)
    assert min(e["seq"] for e in second) > max(e["seq"] for e in first)


def test_no_cast_falls_back_to_narration(client, storyline_id, monkeypatch):
    # No speaker → narration fallback; no LLM call needed.
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hello"}))
    assert [e["type"] for e in events][0] == "narration"


def test_unconfigured_llm_emits_terminal_error_frame(client, storyline_id):
    # No LLM configured → generation raises; the open stream reports a terminal error frame.
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert events[-1]["type"] == "error"


def test_unknown_scenario_returns_404(client):
    assert client.post("/api/play/nope/turn", json={"text": "hi"}).status_code == 404


def test_empty_text_returns_400(client, storyline_id):
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    assert client.post(f"/api/play/{scid}/turn", json={"text": "   "}).status_code == 400


def test_unknown_session_returns_404(client, storyline_id):
    _, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [], sid)
    assert (
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "sessionId": "ps_x"}).status_code
        == 404
    )
