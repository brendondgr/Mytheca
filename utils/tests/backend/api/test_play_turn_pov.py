"""POST /api/play/{scenarioId}/turn — Player POV path.

With ``povCharacterId`` set, the player's line IS that character's line: it is seeded into
the turn as a ``character`` beat (later speakers react to it), persisted on the
``user_turn`` row, and the visible character event is WITHHELD (the client renders the
line optimistically / on rehydrate). The POV character is locked out of the AI roster so
the model never voices a duplicate beat for them; the loop ends on its own once the rest
of the cast is done. LLM is offline-mocked, mirroring ``test_play_turn.py``.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import httpx
from sqlalchemy import select

from app.models import Event
from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    '<type:character_dialogue>\n"I hear you."'
)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch, content: str = _EMISSION):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _plan_routed(monkeypatch, decisions, *, narration="A hush falls over the room.", branches=None):
    """Route the mock by system prompt: intent → freeform, planner → scripted decisions,
    branch → options, narrator → prose, character → an emission echoing the speaker."""
    plan = iter(decisions)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system or "in their own voice" in system:
            return _resp(json.dumps({"choices": branches or []}))
        if "step-by-step loop" in system:
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


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _by_id(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if "id" in e:
            grouped[e["id"]].append(e)
    return grouped


def _reconstruct_dialogue(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for _eid, evs in _by_id(events).items():
        if evs[0]["type"] != "character_dialogue":
            continue
        out.append({"characterId": evs[-1]["data"].get("characterId"), "seq": evs[0]["seq"]})
    return sorted(out, key=lambda d: d["seq"])


def _two(client, storyline_id):
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    return mei, kira, sid


def _scenario(client, storyline_id, cast, setting, **extra):
    body = {"title": "Standoff", "castIds": cast, "settingId": setting, **extra}
    return client.post(f"/api/storylines/{storyline_id}/scenarios", json=body).json()["id"]


def test_pov_line_not_emitted_and_other_char_reacts(client, db_session, storyline_id, monkeypatch):
    # Player speaks AS Mei; Kira reacts. Mei's line is NEVER emitted as a visible character
    # event (the client renders it optimistically), and Kira does speak.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, suggestionsCount=0)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I have nothing to say to you.", "povCharacterId": mei},
        )
    )
    # No visible character beat is attributed to the POV character (Mei)…
    mei_beats = [
        e for e in events
        if e["type"] in ("character_dialogue", "character_action")
        and e.get("data", {}).get("characterId") == mei
    ]
    assert mei_beats == []
    # …and the other present character (Kira) reacted to Mei's line.
    assert [d["characterId"] for d in _reconstruct_dialogue(events)] == [kira]


def test_pov_persisted_on_user_turn_row(client, db_session, storyline_id, monkeypatch):
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, suggestionsCount=0)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    client.post(f"/api/play/{scid}/turn", json={"text": "Say nothing.", "povCharacterId": mei})
    row = db_session.scalars(select(Event).where(Event.type == "user_turn")).one()
    assert row.data["pov"] == mei and row.data["text"] == "Say nothing."


def test_solo_pov_ends_naturally_no_ai_dialogue(client, storyline_id, monkeypatch):
    # The POV character is the only present cast member → nobody is selectable, so the AI
    # voices no one. The turn is just the player's (withheld) line (+ an optional narrator open).
    _configure_llm(client)
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = _scenario(client, storyline_id, [mei], sid, suggestionsCount=0)
    _plan_routed(monkeypatch, [{"action": "end"}])
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I wait alone.", "povCharacterId": mei}))
    assert all(e["type"] != "error" for e in events)
    assert all(e["type"] != "character_dialogue" for e in events)  # the AI voiced no one


def test_stray_speak_pov_is_coerced_to_end(client, storyline_id, monkeypatch):
    # Defensive backstop: even if the planner returns speak(<pov>), the engine ends the turn
    # rather than letting the AI voice the POV character.
    from app.agents import planner_agent
    from app.agents.planner_agent import BeatDecision

    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, suggestionsCount=0)
    _patch_llm(monkeypatch)  # intent → freeform; narrator/character calls harmless here

    calls = {"n": 0}

    def fake_next_beat(db, ctx, intent, turn_beats, acted, *, scene_opening=False, locked_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return BeatDecision("speak", actor_id=mei)  # a stray reply naming the POV char
        return BeatDecision("end")

    monkeypatch.setattr(planner_agent, "next_beat", fake_next_beat)
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I glare.", "povCharacterId": mei, "trace": True},
        )
    )
    # The backstop fired: a plan trace announces the turn ending, and Mei is never voiced.
    assert any(
        e["type"] == "trace" and e["step"] == "plan" and "voiced by the player" in (e.get("detail") or "")
        for e in events
    )
    mei_beats = [
        e for e in events
        if e["type"] in ("character_dialogue", "character_action")
        and e.get("data", {}).get("characterId") == mei
    ]
    assert mei_beats == []


def test_unknown_pov_falls_back_to_narrator_behavior(client, db_session, storyline_id, monkeypatch):
    # A povCharacterId that is not a present cast member degrades to the default guide/
    # narrator behavior: the user_turn row records pov=None (a left-side player line).
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, suggestionsCount=0)
    _plan_routed(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    client.post(f"/api/play/{scid}/turn", json={"text": "hi", "povCharacterId": "ch_not_in_cast"})
    row = db_session.scalars(select(Event).where(Event.type == "user_turn")).one()
    assert row.data["pov"] is None
