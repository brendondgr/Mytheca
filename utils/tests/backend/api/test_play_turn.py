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
    ""
    "Mei doesn't touch the pouch. Her eyes flick once to Kira at the bar, then back.\n"
    ""
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


# `trace`, `error` and `reasoning` frames share the wire with story events but are NOT
# story events — they carry no envelope id/seq and are absent from `story_event_adapter`.
# Reasoning frames are on by default now (Reasoning visibility defaults to `full`), so a
# test that means "every story event" has to say so.
_TRANSPORT_ONLY = ("trace", "error", "reasoning")


def _story(events: list[dict]) -> list[dict]:
    return [e for e in events if e["type"] not in _TRANSPORT_ONLY]


def _by_id(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if "id" in e:  # story events only — trace/error frames carry no envelope id
            grouped[e["id"]].append(e)
    return grouped


def test_a_beat_arrives_as_one_passage_carrying_action_and_speech(
    client, storyline_id, monkeypatch
):
    """Action and speech are no longer separate events — they are one passage."""
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
    assert "character_prose" in types
    assert "character_action" not in types and "character_dialogue" not in types
    passage = [e for e in events if e["type"] == "character_prose"]
    assert all(e["data"]["characterId"] == cid for e in passage)
    whole = "".join(e["data"]["text"] for e in passage)
    assert "doesn't touch the pouch" in whole  # the action
    assert "Coin's easy." in whole  # and the speech, in the same passage


def test_dialogue_delta_chunks_accumulate_to_full_line(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    dialogue_chunks = [e for e in events if e["type"] == "character_prose"]
    assert len(dialogue_chunks) > 1  # actually delta-streamed in pieces
    # all chunks share one id + seq; only the final chunk is done.
    assert len({e["id"] for e in dialogue_chunks}) == 1
    assert len({e["seq"] for e in dialogue_chunks}) == 1
    assert [e["data"]["done"] for e in dialogue_chunks] == [False] * (len(dialogue_chunks) - 1) + [True]
    reconstructed = "".join(e["data"]["text"] for e in dialogue_chunks)
    assert reconstructed.endswith(
        '"Coin\'s easy. It\'s what comes after the coin I don\'t trust."'
    )


def test_reasoning_leak_stripped_from_character_emission(client, storyline_id, monkeypatch):
    # A reasoning model dumps its chain-of-thought + a harmony <channel|> marker before the
    # real markered emission. chat_complete sanitizes centrally, so only the final answer
    # reaches parse_emission — no reasoning, no channel token in the rendered dialogue.
    leaked = (
        "* Constraint check: 5-10 words for action, 1-3 sentences for dialogue.\n"
        '* Dialogue: "A storm is a chaotic thing."\n'
        "<channel|>\n"
        "<speaker:1>\n"
        "slowly circles them, scent intensifying\n"
        '"A storm is a chaotic thing—loud, frantic."'
    )
    _configure_llm(client)
    _patch_llm(monkeypatch, leaked)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    passage = "".join(e["data"]["text"] for e in events if e["type"] == "character_prose")
    # One passage now carries both the physical beat and the spoken line.
    assert '"A storm is a chaotic thing—loud, frantic."' in passage
    assert "slowly circles them" in passage
    # None of the reasoning scaffolding or the channel token leaks into the beat.
    assert "Constraint check" not in passage
    assert "channel" not in passage.lower()


def test_every_streamed_line_validates(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    for e in _story(_stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))):
        story_event_adapter.validate_python(e)


def test_seq_is_monotonic_and_per_event_unique(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _story(_stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})))
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
    first = _story(_stream(client.post(f"/api/play/{scid}/turn", json={"text": "one", "directedAt": cid})))
    session_id = first[0]["sessionId"]
    second = _story(_stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "two", "directedAt": cid, "sessionId": session_id},
        )
    ))
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


def test_internal_thought_streams_as_private_to_user(client, db_session, storyline_id, monkeypatch):
    from sqlalchemy import select

    from app.models import Event

    _configure_llm(client)
    emission = (
        "<speaker:1>\n"
        "<thinking>Coin first, favor later. Let him sweat.</thinking>\n"
        "\"Coin's easy.\""
    )
    _patch_llm(monkeypatch, emission)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))

    # The private thought now streams to the player as its own bubble (feedback #4) …
    thought = next(e for e in events if e["type"] == "internal_thought")
    assert thought["visibility"] == "private_to_user"
    assert thought["data"]["characterId"] == cid and "Let him sweat" in thought["data"]["text"]
    # … and it is persisted with the same visibility.
    rows = db_session.scalars(select(Event).where(Event.type == "internal_thought")).all()
    assert len(rows) == 1
    assert rows[0].visibility == "private_to_user"
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
        if "SITUATION-BASED follow-up" in system:  # branch / follow-up suggestions
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
        return _resp(f'<speaker:{num}>\n"{name} speaks now."')

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
    assert "narration" in types and "character_prose" in types
    assert types.index("narration") < types.index("character_prose")  # the narrator leads


def test_no_narration_when_planner_does_not_ask(client, storyline_id, monkeypatch):
    # A DIRECTED turn (no scene-opening narration): with the planner only asking a
    # character to speak, no narrator beat is inserted.
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "narration" for e in events)


def test_scene_opens_with_narration_before_any_character(client, storyline_id, monkeypatch):
    # Cold open, freeform (no directed character): the NARRATOR opens the scene — a
    # character never speaks first (feedback #1). Planner ends after the opening.
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "end"}])
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I step inside."}))
    types = [e["type"] for e in events if e["type"] in ("narration", "character_prose")]
    assert types and types[0] == "narration"  # the narrator opens
    # No character dialogue precedes the opening narration.
    dialogue = [e for e in events if e["type"] == "character_prose"]
    if dialogue:
        first_narration_seq = next(e["seq"] for e in events if e["type"] == "narration")
        assert min(e["seq"] for e in dialogue) > first_narration_seq


def test_branch_outcome_opens_with_progression_narration(client, storyline_id, monkeypatch):
    # Selecting a path (``outcome`` set) opens with a fuller "progression" narration that
    # plays the choice out (feedback #2), then the scene reacts.
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], narration="The doors slam wide.")
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Press her", "outcome": "escalate the confrontation", "trace": True},
        )
    )
    types = [e["type"] for e in events]
    assert "narration" in types  # progression narration led the turn
    # A plan trace announces the choice being played out.
    plan = next(t for t in events if t["type"] == "trace" and t["step"] == "plan" and t["data"].get("outcome"))
    assert plan["data"]["outcome"] == "escalate the confrontation"


def test_scene_max_turns_counts_the_narrated_open(client, storyline_id, monkeypatch):
    # The per-scene ceiling counts EVERY beat, narration included (request #3). A freeform
    # opening turn narrates the scene first (beat 1), so with max_turns=2 exactly ONE
    # character reply runs even though the planner would keep going.
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [
            {"action": "speak", "actor": 1},
            {"action": "speak", "actor": 2},
            {"action": "speak", "actor": 3},
            {"action": "speak", "actor": 4},
            {"action": "end"},
        ],
    )
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in ("Ana", "Bo", "Cy", "Di")
    ]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Cap", "castIds": ids, "settingId": sid, "maxTurns": 2},
    ).json()["id"]
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "I address the room.", "trace": True})
    )
    # The narrated open consumed a beat, so only the FIRST planned speaker ran before the cap.
    assert any(e.get("type") == "narration" for e in events)  # the scene-setting open
    assert [d["characterId"] for d in _reconstruct_dialogue(events)] == ids[:1]
    limit = next(
        t for t in events if t["type"] == "trace" and t["step"] == "plan"
        and "turn limit" in (t.get("title") or "").lower()
    )
    assert "scene cap of 2" in (limit.get("detail") or "")


def test_scene_max_turns_counts_midturn_narration(client, storyline_id, monkeypatch):
    # A narrator beat inserted BETWEEN speakers also counts toward the cap: addressing a
    # character suppresses the cold open, so the only narration is the mid-turn one — with
    # max_turns=2 that leaves room for a single reply before the cap.
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [
            {"action": "speak", "actor": 1},
            {"action": "narrate"},
            {"action": "speak", "actor": 1},
            {"action": "end"},
        ],
    )
    cid, sid = _refs(client, storyline_id)
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Mid", "castIds": [cid], "settingId": sid, "maxTurns": 2},
    ).json()["id"]
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Speak to me.", "directedAt": cid, "trace": True},
        )
    )
    # reply (beat 1) + mid-turn narration (beat 2) → cap; the second scripted reply is cut.
    assert len(_reconstruct_dialogue(events)) == 1
    assert any(e.get("type") == "narration" for e in events)  # the mid-turn interstitial
    limit = next(
        t for t in events if t["type"] == "trace" and t["step"] == "plan"
        and "turn limit" in (t.get("title") or "").lower()
    )
    assert "scene cap of 2" in (limit.get("detail") or "")


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
        return _resp(f'<speaker:{num}>\n"{name} speaks now."')

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
        '"Don\'t pretend you forgot."\n'
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
        '"Fine."\n'
        '<type:state_update>\n{"key":"mana","delta":5}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "state_update" for e in events)  # unknown stat dropped


def test_branch_choices_emitted_at_end_of_turn_regardless_of_needs_branch(client, storyline_id, monkeypatch):
    # Suggestions are now count-driven (default suggestions_count=4): they appear at the
    # end of the turn even though the planner never sets needsBranch (Scene Dialogue Updates).
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [{"action": "speak", "actor": 1}, {"action": "end"}],  # note: NO needsBranch
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


def test_no_suggestions_when_scene_count_is_zero(client, storyline_id, monkeypatch):
    # suggestions_count=0 disables follow-ups entirely — no branch_choices event.
    _configure_llm(client)
    _plan_routed(
        monkeypatch,
        [{"action": "speak", "actor": 1}, {"action": "end"}],
        branches=[{"label": "Back off", "outcome": "de-escalate"}],
    )
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Quiet", "castIds": [mei], "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I press her.", "directedAt": mei}))
    assert all(e["type"] != "branch_choices" for e in events)


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
        " Then bloom for me, my precious thing. "
        '</type:state_update> {"key": "sensation", "delta": 10, "reason": "the grove"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))

    # No visible event carries a raw emission tag or the raw stat JSON.
    for e in events:
        text = e.get("data", {}).get("text", "")
        assert "type:" not in text and "{" not in text
    # A proper dialogue bubble + a real state_update (not prose) both arrived.
    dialogue = "".join(e["data"]["text"] for e in events if e["type"] == "character_prose")
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
    assert any(e["type"] == "character_prose" for e in events)
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
        if evs[0]["type"] != "character_prose":
            continue
        out.append(
            {
                "characterId": evs[-1]["data"].get("characterId"),
                "text": "".join(e["data"]["text"] for e in evs),
                "seq": evs[0]["seq"],
            }
        )
    return sorted(out, key=lambda d: d["seq"])


def test_later_speakers_are_no_longer_held_for_a_continuity_check(client, storyline_id, monkeypatch):
    """Every beat goes straight to the wire — there is no auditor call and no hold.

    The continuity guard used to inspect a COMPLETE candidate line before a later beat
    could be shown, which cost ~10 s per second speaker (EXP-2026-08-005 put it at 11 %
    of turn time) and was the only reason a later beat could not stream as it was
    written. It is gone; this pins that it stays gone.
    """
    _configure_llm(client)
    mei, kira, _jax, sid = _three(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)

    plan = iter([{"action": "speak", "actor": 1}, {"action": "speak", "actor": 2}, {"action": "end"}])
    auditor_calls: list[str] = []

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
        if "continuity auditor" in system:
            auditor_calls.append(system)
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num = m.group(1) if m else "1"
        if num == "1":
            return _resp('<speaker:1>\n"The lantern is lit."')
        return _resp('<speaker:2>\n"I step toward it."')

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "I address the room.", "trace": True})
    )

    texts = [line["text"] for line in _reconstruct_dialogue(events)]
    assert any(t == '"The lantern is lit."' for t in texts)   # first speaker
    assert any(t == '"I step toward it."' for t in texts)     # second speaker, unheld
    assert auditor_calls == []                                 # no extra LLM round trip
    assert all(e.get("step") != "consistency" for e in events if e["type"] == "trace")


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


def test_trace_is_persisted_even_when_not_streamed(client, db_session, storyline_id, monkeypatch):
    # The diagnostic trace is ALWAYS saved (so a reopened scene's graph/RAG activity survives
    # for review/export), independent of whether the caller streamed it (`trace` off here).
    from app.models import TurnTrace

    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid}))
    assert all(e["type"] != "trace" for e in events)  # nothing streamed …

    rows = db_session.query(TurnTrace).order_by(TurnTrace.turn, TurnTrace.n).all()
    steps = [r.step for r in rows]
    assert steps and steps[0] == "turn"  # … but the full trace is persisted, opening with `turn`
    assert {"lore", "commit"} <= set(steps)  # incl. the RAG look-up + graph commit
    assert [r.n for r in rows] == sorted(r.n for r in rows)  # ordered

    # The session was touched so resume can pick the most recent play-through.
    from app.models import PlaySession

    session = db_session.get(PlaySession, events[0]["sessionId"])
    assert session.updated_at is not None


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
        if e["type"] not in _TRANSPORT_ONLY:
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


def test_trace_marks_the_turn_ending_step_structurally(client, storyline_id, monkeypatch):
    # The step that stops the beat loop carries `data.end = True` — the structured signal the
    # story player's turn-status strip reads, so no client has to match on the prose title.
    _configure_llm(client)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end", "reason": "said"}])
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "I address the room.", "trace": True})
    )
    ends = [
        t
        for t in events
        if t["type"] == "trace" and t["step"] == "plan" and t["data"].get("end") is True
    ]
    assert len(ends) == 1  # exactly one end-of-loop marker per turn
    # It is the LAST plan step of the turn — nothing plans a further beat after it.
    plans = [t for t in events if t["type"] == "trace" and t["step"] == "plan"]
    assert plans[-1] is ends[0]


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
        '"Don\'t pretend you forgot."\n'
        '<type:state_update>\n{"key":"suspicion","delta":12,"reason":"old guilt"}'
    )
    _patch_llm(monkeypatch, emission)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    commit = next(t for t in events if t["type"] == "trace" and t["step"] == "commit")
    assert commit["data"]["consequences"] == 1  # the stat change is a durable consequence
    # …and the Graph trace now names WHAT changed, not just a count.
    assert commit["data"]["changes"] and "suspicion" in commit["detail"]
    assert "old guilt" in commit["detail"]
    # …and the change itself is a "stat" step with the clamped value + reason.
    stat = next(t for t in events if t["type"] == "trace" and t["step"] == "stat")
    assert stat["data"]["value"] == 62 and "old guilt" in stat["detail"]


def test_trace_surfaces_hidden_thinking(client, storyline_id, monkeypatch):
    _configure_llm(client)
    emission = (
        "<speaker:1>\n<thinking>Coin first, favor later.</thinking>\n"
        '"Fine."'
    )
    _patch_llm(monkeypatch, emission)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    # The thought streams as a private_to_user bubble …
    assert any(e["type"] == "internal_thought" for e in events)
    # … and the Inspector trace ALSO surfaces it so the reasoning is visible there.
    think = next(t for t in events if t["type"] == "trace" and t["step"] == "thinking")
    assert "Coin first" in think["detail"]


def _patch_llm_with_usage(monkeypatch, prompt_tokens: int, content: str = _EMISSION):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 40},
            },
        )

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_context_trace_reports_exact_prompt_tokens(client, db_session, storyline_id, monkeypatch):
    # When the model reports usage.prompt_tokens, the engine emits a `context` trace step
    # carrying the EXACT input-token count — the real "context window used" for the dial —
    # and persists it so a resumed scene can seed the dial without re-running a turn.
    from app.models import TurnTrace

    _configure_llm(client)
    _patch_llm_with_usage(monkeypatch, 4096)
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    ctx = next(t for t in events if t["type"] == "trace" and t["step"] == "context")
    assert ctx["data"]["promptTokens"] == 4096
    assert ctx["data"]["characterId"] == cid

    # Persisted (regardless of the stream opt-in) so resume rehydrates the real value.
    rows = db_session.query(TurnTrace).filter(TurnTrace.step == "context").all()
    assert rows and rows[-1].data["promptTokens"] == 4096


def test_context_trace_reports_no_token_count_when_the_endpoint_omits_usage(
    client, storyline_id, monkeypatch
):
    """No usage block → no `promptTokens`, so the dial keeps its char/4 fallback.

    The step itself still appears: it also carries the locally-computed reusable-prefix
    figure, which does not depend on the endpoint reporting anything. That is deliberate —
    vLLM omits its own cache counter exactly when the hit is zero, so a prompt-cache
    regression would otherwise look like missing data instead of a number going down.
    """
    _configure_llm(client)
    _patch_llm(monkeypatch)  # the default mock omits `usage`
    cid, sid = _refs(client, storyline_id)
    scid = _scenario(client, storyline_id, [cid], sid)
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True})
    )
    steps = [e for e in events if e["type"] == "trace" and e["step"] == "context"]
    assert all("promptTokens" not in e["data"] for e in steps)
    assert all("reusablePrefixChars" in e["data"] for e in steps)


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
        return _resp(f'<speaker:{num}>\n"{name} speaks now."')

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
        '"I know what you did, Beth."\n'
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
    dialogue = "".join(e["data"]["text"] for e in events if e["type"] == "character_prose")
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


def _route_llm(monkeypatch, *, planner_replies: list[str], other: str = _EMISSION):
    """Route chat/completions by agent (system-prompt marker); planner replies in order."""
    state = {"planner": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode())
        system = body["messages"][0]["content"]
        if "scene director running one interactive-story turn" in system:
            i = min(state["planner"], len(planner_replies) - 1)
            state["planner"] += 1
            content = planner_replies[i]
        else:
            content = other
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_planner_exit_emits_status_change_and_stops_selection(client, storyline_id, monkeypatch):
    # The planner's first beat removes Mei (dead); after that only Kira remains present, so
    # the exit both emits a character_status_change and prevents Mei being picked to speak.
    _configure_llm(client)
    cid_mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    cid_kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid_mei, cid_kira], "suggestionsCount": 0},
    ).json()["id"]
    _route_llm(
        monkeypatch,
        planner_replies=[
            json.dumps({"action": "exit", "actor": 1, "status": "dead", "reason": "run through"}),
            json.dumps({"action": "end", "reason": "done"}),
        ],
    )
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I run Mei through."}))
    status_events = [e for e in events if e["type"] == "character_status_change"]
    assert len(status_events) == 1
    data = status_events[0]["data"]
    assert data["characterId"] == cid_mei and data["status"] == "dead" and data["auto"] is True
    # Mei never speaks after being removed (no dialogue attributed to her).
    mei_lines = [e for e in events if e.get("data", {}).get("characterId") == cid_mei and e["type"] in ("character_prose",)]
    assert mei_lines == []


def test_status_change_persists_and_folds_into_presence(client, storyline_id, monkeypatch, db_session):
    # The streamed status change is persisted, so presence.current_presence sees it on the
    # session — the same durable fold the next turn's assembler reads.
    from app.services import presence

    _configure_llm(client)
    cid_mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    cid_kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid_mei, cid_kira], "suggestionsCount": 0},
    ).json()["id"]
    _route_llm(
        monkeypatch,
        planner_replies=[
            json.dumps({"action": "exit", "actor": 1, "status": "left", "reason": "storms out"}),
            json.dumps({"action": "end"}),
        ],
    )
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Mei, get out."}))
    session_id = next(e["sessionId"] for e in events if e.get("type") == "character_status_change")
    assert presence.current_presence(db_session, session_id).get(cid_mei) == "left"


_HEALTH_EMISSION = (
    "<speaker:1>\n"
    "Mei crumples to the floor\n"
    '<type:state_update>\n{"key": "health", "delta": -100, "reason": "stabbed"}'
)

_LEAVE_EMISSION = (
    "<speaker:1>\n"
    "turns and walks out\n"
    '<type:presence_change>\n{"status": "left", "reason": "done here"}'
)


def test_health_floor_auto_knocks_unconscious(client, storyline_id, monkeypatch, db_session):
    # A vital stat (health) clamped to its floor deterministically knocks the character out.
    from app.models.stat import StatDefinition

    db_session.add(
        StatDefinition(storyline_id=storyline_id, key="health", display_name="Health", min=0, max=100, default=100)
    )
    db_session.commit()
    _configure_llm(client)
    _patch_llm(monkeypatch, _HEALTH_EMISSION)
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I stab Mei.", "directedAt": cid}))
    status = [e for e in events if e["type"] == "character_status_change"]
    assert len(status) == 1
    assert status[0]["data"]["characterId"] == cid
    assert status[0]["data"]["status"] == "unconscious" and status[0]["data"]["auto"] is True


def test_self_declared_exit_removes_character(client, storyline_id, monkeypatch, db_session):
    # A character declaring <type:presence_change> leaves the scene (folds into presence).
    from app.services import presence

    _configure_llm(client)
    _patch_llm(monkeypatch, _LEAVE_EMISSION)
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "Mei, leave.", "directedAt": cid}))
    status = [e for e in events if e["type"] == "character_status_change"]
    assert len(status) == 1 and status[0]["data"]["status"] == "left"
    session_id = status[0]["sessionId"]
    assert presence.current_presence(db_session, session_id).get(cid) == "left"
