"""POST /api/play/{scenarioId}/turn — POV generation + delta-streamed transport.

LLM is offline-mocked (httpx.MockTransport returning a thin-tag emission), mirroring
the agent tests. Visible dialogue delta-streams (same id + seq, incremental text,
``done`` flag); the client reconstructs by id.
"""

from __future__ import annotations

import json
import re
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


def test_internal_thought_persisted_hidden_and_withheld(client, db_session, storyline_id, monkeypatch):
    from sqlalchemy import select

    from app.models import Event

    _configure_llm(client)
    emission = (
        "<speaker:1>\n"
        "<thinking>Coin first, favor later. Let him sweat.</thinking>\n"
        "<type:character_dialogue>\n\"Coin's easy.\""
    )
    _patch_llm(monkeypatch, emission)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))

    # Hidden thinking is never placed on the wire …
    assert all(e["type"] != "internal_thought" for e in events)
    # … but it is persisted with visibility hidden, as conditioning context.
    rows = db_session.scalars(select(Event).where(Event.type == "internal_thought")).all()
    assert len(rows) == 1
    assert rows[0].visibility == "hidden"
    assert "Let him sweat" in rows[0].data["text"]


# ---- P5: Director (speaker queue) + Narrator interstitials --------------------


def _patch_routed(monkeypatch, *, director_speakers, narration="A hush falls over the room."):
    """Route the mock by system prompt: director → JSON, narrator → prose, character →
    an emission echoing the prompt's speaker number/name."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "scene director" in system:
            payload = json.dumps({"speakers": director_speakers, "needsBranch": False, "beat": "x"})
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})
        if "narrator of an interactive scene" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": narration}}]})
        user = body["messages"][1]["content"]
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "Someone")
        emission = f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now."'
        return httpx.Response(200, json={"choices": [{"message": {"content": emission}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_two_speaker_turn_streams_in_director_order(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_routed(monkeypatch, director_speakers=[1, 2])
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei, kira], sid)
    # No directedAt → the Director escalates and returns [1, 2] = [Mei, Kira].
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I address the room."}))
    dialogue = [e for e in events if e["type"] == "character_dialogue" and e["data"]["done"]]
    speakers_in_order = [e["data"]["characterId"] for e in dialogue]
    assert speakers_in_order == [mei, kira]


def test_narrator_mode_inserts_an_interstitial_before_the_speaker(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_routed(monkeypatch, director_speakers=[1])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "mode": "narrator"})
    )
    types = [e["type"] for e in events]
    assert "narration" in types and "character_dialogue" in types
    n_idx = types.index("narration")
    d_idx = types.index("character_dialogue")
    assert n_idx < d_idx  # the narrator beat leads


def test_pov_mode_emits_no_narration(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_routed(monkeypatch, director_speakers=[1])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "narration" for e in events)


# ---- P8: stat changes (validated + clamped) + branch choices ------------------


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_stat_change_streams_clamped_state_update_and_applies(client, storyline_id, monkeypatch):
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "suspicion", "displayName": "Suspicion", "min": 0, "max": 100, "default": 50},
    )
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    emission = (
        "<speaker:1>\n"
        '<type:character_dialogue>\n"Don\'t pretend you forgot."\n'
        '<type:state_update>\n{"key":"suspicion","delta":12,"reason":"old guilt, raised guard"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    su = next(e for e in events if e["type"] == "state_update")
    assert su["data"]["stat"]["key"] == "suspicion"
    assert su["data"]["stat"]["value"] == 62  # default 50 + 12
    assert su["data"]["stat"]["reason"] == "old guilt, raised guard"
    # applied on the hot path (clamped) to the character
    assert client.get(f"/api/characters/{cid}/stats").json()["suspicion"] == 62


def test_unknown_proposed_stat_is_dropped_no_event(client, storyline_id, monkeypatch):
    _configure_llm(client)
    cid, sid = _refs(client, storyline_id)  # no stats defined on this world
    scid = _scenario(client, storyline_id, [cid], sid)
    emission = (
        "<speaker:1>\n"
        '<type:character_dialogue>\n"Fine."\n'
        '<type:state_update>\n{"key":"mana","delta":5}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "state_update" for e in events)  # unknown stat dropped


def test_branch_choices_emitted_when_director_flags_a_fork(client, storyline_id, monkeypatch):
    _configure_llm(client)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "faces a fork" in system:
            return _resp(json.dumps({"choices": [{"label": "Back off", "outcome": "de-escalate"}, {"label": "Press her", "outcome": "escalate"}]}))
        if "scene director" in system:
            return _resp(json.dumps({"speakers": [1], "needsBranch": True, "beat": "fork"}))
        user = body["messages"][1]["content"]
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "X")
        return _resp(f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now."')

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei, kira], sid)
    # No directedAt → the reasoned Director runs and flags needsBranch.
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I press the room."}))
    branch = next(e for e in events if e["type"] == "branch_choices")
    labels = [c["label"] for c in branch["data"]["choices"]]
    assert labels == ["Back off", "Press her"]
    assert all("check" not in c for c in branch["data"]["choices"])  # no dice


def test_closing_style_tags_do_not_leak_into_the_stream(client, storyline_id, monkeypatch):
    # Regression: a model that emits </type:…> delimiters + a trailing stat JSON must
    # still stream a clean dialogue bubble + a real state_update event — no leaked tags.
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "sensation", "displayName": "Sensation", "min": 0, "max": 100, "default": 10},
    )
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    emission = (
        "<speaker:1>\n"
        "<type:character_action> Sylvarra glides forward, tracing a slow line. "
        "</type:character_dialogue> Then bloom for me, my precious thing. "
        '</type:state_update> {"key": "sensation", "delta": 10, "reason": "the grove"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))

    # No visible event carries a raw emission tag or the raw stat JSON.
    for e in events:
        text = e.get("data", {}).get("text", "")
        assert "type:" not in text and "{" not in text
    # A proper dialogue bubble + a real state_update (not prose) both arrived.
    dialogue = "".join(e["data"]["text"] for e in events if e["type"] == "character_dialogue")
    assert "Then bloom for me, my precious thing." in dialogue
    su = next(e for e in events if e["type"] == "state_update")
    assert su["data"]["stat"]["key"] == "sensation" and su["data"]["stat"]["value"] == 20


# ---- P9: read-time reflection interlude ---------------------------------------


class _FakeRedis:
    """Minimal in-memory Redis for interior-state string ops."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


def test_turn_writes_interior_state_after_stream(client, storyline_id, monkeypatch):
    from app.memory import interior

    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        system = json.loads(request.content.decode())["messages"][0]["content"]
        if "private inner voice" in system:  # the reflection agent
            payload = json.dumps({"disposition": "Guarded now.", "retrospective": "He pushed."})
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))

    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))

    # The visible stream is unaffected (reflection is off the hot path) …
    assert any(e["type"] == "character_dialogue" for e in events)
    assert all(e["type"] != "error" for e in events)
    # … and the speaker's interior state was written for the next turn to read.
    session_id = events[0]["sessionId"]
    rec = interior.get_interior(session_id, cid)
    assert rec is not None and rec.disposition == "Guarded now."


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
