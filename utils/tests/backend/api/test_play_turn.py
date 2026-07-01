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
        if "id" in e:  # story events only — trace/error frames carry no envelope id
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


# ---- ReAct planner: dynamic speaker order, uncapped, narrator beats -----------


def _plan_routed(monkeypatch, decisions, *, narration="A hush falls over the room.", branches=None):
    """Route the mock by system prompt: intent → freeform, planner → scripted decisions
    (consumed in order; ``end`` once exhausted), branch → options, narrator → prose,
    character → an emission echoing the prompt's speaker number/name."""
    plan = iter(decisions)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:  # intent
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "faces a fork" in system:  # branch options
            return _resp(json.dumps({"choices": branches or []}))
        if "step-by-step loop" in system:  # ReAct planner
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp(narration)
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "Someone")
        return _resp(f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now."')

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_planner_runs_speakers_in_order(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [{"action": "speak", "actor": 1}, {"action": "speak", "actor": 2}, {"action": "end"}],
    )
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei, kira], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I address the room."}))
    assert [d["characterId"] for d in _reconstruct_dialogue(events)] == [mei, kira]


def test_planner_can_insert_a_narrator_beat(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "narrate"}, {"action": "speak", "actor": 1}, {"action": "end"}])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    types = [e["type"] for e in _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi"}))]
    assert "narration" in types and "character_dialogue" in types
    assert types.index("narration") < types.index("character_dialogue")  # the narrator leads


def test_no_narration_when_planner_does_not_ask(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi"}))
    assert all(e["type"] != "narration" for e in events)


def test_broadcast_runs_the_whole_cast_uncapped(client, storyline_id, monkeypatch):
    # "Everyone introduces themselves" → four characters act in sequence (past the old
    # 3-speaker cap), driven by the planner's broadcast walk.
    _configure_llm(client)
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in ("Ana", "Bo", "Cy", "Di")
    ]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}).json()["id"]
    scid = _scenario(client, storyline_id, ids, sid)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "broadcast", "scope": "all", "directive": "all introduce"}))
        if "step-by-step loop" in system:
            return _resp("not json")  # force the planner's broadcast heuristic (walk the cast)
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "X")
        return _resp(f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now."')

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Everyone introduces themselves."}))
    assert [d["characterId"] for d in _reconstruct_dialogue(events)] == ids  # all four, in order


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


def test_branch_choices_emitted_when_planner_flags_a_fork(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [{"action": "speak", "actor": 1}, {"action": "end", "needsBranch": True}],
        branches=[{"label": "Back off", "outcome": "de-escalate"}, {"label": "Press her", "outcome": "escalate"}],
    )
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei, kira], sid)
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


# ---- P10: multi-party (consistency guard · live queue re-rank · universal reflection) --


def _three(client, storyline_id):
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    jax = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Jax"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    return mei, kira, jax, sid


def _reconstruct_dialogue(events: list[dict]) -> list[dict]:
    """Collapse delta chunks → one {characterId, text, seq} per dialogue event, seq-ordered."""
    out: list[dict] = []
    for eid, evs in _by_id(events).items():
        if evs[0]["type"] != "character_dialogue":
            continue
        out.append(
            {
                "characterId": evs[-1]["data"].get("characterId"),
                "text": "".join(e["data"]["text"] for e in evs),
                "seq": evs[0]["seq"],
            }
        )
    return sorted(out, key=lambda d: d["seq"])


def test_consistency_guard_regenerates_a_contradicting_later_line(client, storyline_id, monkeypatch):
    _configure_llm(client)
    mei, kira, _jax, sid = _three(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    plan = iter([{"action": "speak", "actor": 1}, {"action": "speak", "actor": 2}, {"action": "end"}])

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "step-by-step loop" in system:
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:  # flag Kira's first attempt
            return _resp(json.dumps({"consistent": False, "reason": "the lantern was just lit"}))
        if "private inner voice" in system:
            return _resp("{}")
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num = m.group(1) if m else "1"
        if num == "1":
            return _resp('<speaker:1>\n<type:character_dialogue>\n"The lantern is lit."')
        if "broke continuity" in user:  # Kira's redo
            return _resp('<speaker:2>\n<type:character_dialogue>\n"I step toward the lit lantern."')
        return _resp('<speaker:2>\n<type:character_dialogue>\n"The lantern is dark."')  # contradiction

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I address the room."}))

    texts = [line["text"] for line in _reconstruct_dialogue(events)]
    assert any(t == '"The lantern is lit."' for t in texts)  # Mei (first speaker, no guard)
    assert any("lit lantern" in t for t in texts)  # Kira's corrected line
    assert all("dark" not in t for t in texts)  # the contradiction was never emitted


def test_universal_reflection_writes_interior_for_the_whole_cast(client, storyline_id, monkeypatch):
    from app.memory import interior

    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    mei, kira, jax, sid = _three(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira, jax], sid)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "private inner voice" in system:  # every character reflects, even the silent ones
            name = re.search(r"You are (\w+)", user)
            who = name.group(1) if name else "?"
            return _resp(json.dumps({"disposition": f"{who} took it in."}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        return _resp(_EMISSION)  # only Mei is addressed → the sole speaker

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": mei}))

    # Only Mei spoke, but in a crowd (N>2) all three updated their interior state.
    session_id = events[0]["sessionId"]
    for cid in (mei, kira, jax):
        rec = interior.get_interior(session_id, cid)
        assert rec is not None and rec.disposition.endswith("took it in.")


# ---- Inspector: opt-in diagnostic trace frames --------------------------------


def test_no_trace_frames_by_default(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "trace" for e in events)  # off unless requested


def test_trace_frames_when_requested_and_story_events_still_validate(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    traces = [e for e in events if e["type"] == "trace"]
    steps = [t["step"] for t in traces]
    assert steps[0] == "turn"  # each turn opens with a "turn" step
    # The whole pipeline is visible: intent, scene assembly, RAG look-up, the ReAct plan,
    # the speaker, the graph commit, and the reflection interlude.
    assert {"intent", "assemble", "lore", "plan", "speaker", "commit", "reflection"} <= set(steps)
    ns = [t["n"] for t in traces]
    assert ns == sorted(ns) and len(set(ns)) == len(ns)  # ordered, unique
    # Trace frames are transport-only; every real story event still validates.
    for e in events:
        if e["type"] not in ("trace", "error"):
            story_event_adapter.validate_python(e)


def test_trace_plan_step_names_the_next_actor(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _plan_routed(
        monkeypatch, [{"action": "speak", "actor": 1, "reason": "most provoked"}, {"action": "end"}]
    )
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei, kira], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "I address the room.", "trace": True})
    )
    plan = next(t for t in events if t["type"] == "trace" and t["step"] == "plan" and t["data"].get("actor"))
    assert plan["data"]["actor"] == "Mei" and plan["detail"]  # names who's up + why


def test_trace_commit_reports_graph_changes_on_a_stat_turn(client, storyline_id, monkeypatch):
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
        '<type:state_update>\n{"key":"suspicion","delta":12,"reason":"old guilt"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    commit = next(t for t in events if t["type"] == "trace" and t["step"] == "commit")
    assert commit["data"]["consequences"] == 1  # the stat change is a durable consequence
    # …and the change itself is a "stat" step with the clamped value + reason.
    stat = next(t for t in events if t["type"] == "trace" and t["step"] == "stat")
    assert stat["data"]["value"] == 62 and "old guilt" in stat["detail"]


def test_trace_surfaces_hidden_thinking(client, storyline_id, monkeypatch):
    _configure_llm(client)
    emission = (
        "<speaker:1>\n<thinking>Coin first, favor later.</thinking>\n"
        '<type:character_dialogue>\n"Fine."'
    )
    _patch_llm(monkeypatch, emission)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    # The thought never rides the wire as a story event …
    assert all(e["type"] != "internal_thought" for e in events)
    # … but the Inspector trace surfaces it so the reasoning is visible.
    think = next(t for t in events if t["type"] == "trace" and t["step"] == "thinking")
    assert "Coin first" in think["detail"]


# ---- Reactive Turn Director P1: puppet performance + attribution ---------------


def test_puppeted_character_performs_then_target_reacts(client, storyline_id, monkeypatch):
    _configure_llm(client)
    beth = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Beth"}).json()["id"]
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [beth, mei], sid)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:  # intent → puppet Beth, addressed Mei
            return _resp(
                json.dumps(
                    {"kind": "puppet", "actors": [1], "addressed": [2], "scope": "some",
                     "directive": "Beth tells Mei she hates her"}
                )
            )
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "X")
        return _resp(f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now."')

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Beth tells Mei 'I hate you'.", "trace": True})
    )

    # Beth PERFORMS first (the player directed her); Mei then reacts — not Mei answering
    # the player's narration, and not a bystander.
    order = [d["characterId"] for d in _reconstruct_dialogue(events)]
    assert order == [beth, mei]
    intent = next(t for t in events if t["type"] == "trace" and t["step"] == "intent")
    assert intent["data"]["kind"] == "puppet"
    perf = next(
        t for t in events if t["type"] == "trace" and t["step"] == "speaker" and t["data"].get("puppet")
    )
    assert perf["data"]["characterId"] == beth  # Beth's beat is flagged a puppet performance


# ---- Reactive Turn Director P5: relationship changes during play --------------


def test_relationship_update_records_a_relational_consequence(client, storyline_id, monkeypatch):
    _configure_llm(client)
    beth = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Beth"}).json()["id"]
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [beth, mei], sid)
    # Mei (addressed) speaks and declares a relationship shift toward Beth.
    emission = (
        "<speaker:2>\n"
        '<type:character_dialogue>\n"I know what you did, Beth."\n'
        '<type:relationship_update>\n{"target": "Beth", "type": "resents", "reason": "the betrayal"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": mei, "trace": True})
    )
    # A relationship_change trace fires with the resolved source/target/type …
    change = next(t for t in events if t["type"] == "trace" and t["step"] == "relationship_change")
    assert change["data"]["type"] == "resents" and change["data"]["target"] == "Beth"
    # … and it is recorded as a durable consequence (which the cold path writes as a graph edge).
    commit = next(t for t in events if t["type"] == "trace" and t["step"] == "commit")
    assert commit["data"]["consequences"] >= 1
    # No leaked JSON in the visible dialogue.
    dialogue = "".join(e["data"]["text"] for e in events if e["type"] == "character_dialogue")
    assert "know what you did" in dialogue and "{" not in dialogue


# ---- Reactive Turn Director P6: live relationships route ----------------------


def test_relationships_route_empty_when_graph_off(client, storyline_id):
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    resp = client.get(f"/api/play/{scid}/relationships")
    assert resp.status_code == 200
    assert resp.json()["relationships"] == []  # Neo4j disabled in tests → seed fallback


def test_relationships_route_unknown_scenario_404(client):
    assert client.get("/api/play/nope/relationships").status_code == 404


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
