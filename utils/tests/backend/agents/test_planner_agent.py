"""ReAct planner — next-beat parse (speak/narrate/end), roster-constrained, fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.agents.intent_agent import TurnIntent
from app.models import Scenario
from app.services import assembler, llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _cast(*ids: str) -> list[assembler.CastMember]:
    return [
        assembler.CastMember(id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={})
        for i in ids
    ]


def _ctx(cast) -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id="e",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )


def test_speak_resolves_actor_and_addressing(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 2, "addressing": 1, "reason": "provoked"}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "kira" and d.addressing_id == "mei"
    assert d.reason == "provoked"


def test_guidance_reaches_the_planner_prompt(client, db_session, monkeypatch):
    # A selected follow-up suggestion nudges the planner's next-beat decision.
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    _configure_llm(client)
    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    ctx = _ctx(_cast("mei", "kira"))
    ctx.guidance = "reveal the hidden letter"
    planner_agent.next_beat(db_session, ctx, TurnIntent(), [], [])
    assert "steer the scene toward: reveal the hidden letter" in seen["user"]


def test_narrate_action(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "narrate", "reason": "set the scene"}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [])
    assert d.action == "narrate"


def test_end_carries_needs_branch(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "end", "needsBranch": True}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "end" and d.needs_branch is True


def test_out_of_roster_actor_falls_back(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 9}))
    # freeform intent, nothing acted → the fallback opens with the first cast member.
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "mei"


def test_broadcast_fallback_walks_the_cast(db_session):
    # No LLM configured → the fallback honors scope=all, picking the next un-acted member.
    ctx = _ctx(_cast("a", "b", "c"))
    intent = TurnIntent(kind="broadcast", scope="all")
    assert planner_agent.next_beat(db_session, ctx, intent, [], []).actor_id == "a"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a"]).actor_id == "b"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a", "b"]).actor_id == "c"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a", "b", "c"]).action == "end"


def test_addressed_fallback_reacts_then_ends(db_session):
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="direct", addressed=["kira"])
    assert planner_agent.next_beat(db_session, ctx, intent, [], []).actor_id == "kira"
    # once the addressed character has acted, the direction is satisfied.
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["kira"]).action == "end"


def test_scene_opening_freeform_does_not_force_a_speaker(db_session):
    # Cold open + freeform (no LLM → fallback): the narrator opens the scene (engine), so
    # the planner does NOT force a character. Mid-scene freeform still gets a responder.
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent()  # freeform
    assert planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=True).action == "end"
    assert (
        planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=False).actor_id == "mei"
    )


def test_scene_opening_still_honors_a_directed_character(db_session):
    # Even at a cold open, an explicitly addressed character reacts (the player directed them).
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="direct", addressed=["kira"])
    assert (
        planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=True).actor_id == "kira"
    )


def test_no_cast_ends(db_session):
    assert planner_agent.next_beat(db_session, _ctx([]), TurnIntent(), [], []).action == "end"


def test_malformed_reply_falls_back(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json at all")
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "mei"  # opening fallback
