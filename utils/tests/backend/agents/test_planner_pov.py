"""ReAct planner — Player POV roster lock (`locked_id`).

The POV character (the one the player is speaking AS) must never be selectable: it is
dropped from the roster the model sees and from every offline fallback branch, so the AI
never voices a second beat for them and the loop ends on its own once the rest are done.
"""

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


def test_locked_pov_dropped_from_roster_so_numbers_shift(client, db_session, monkeypatch):
    # Mei is the POV character → the roster the model numbers is just [Kira], so actor 1 = Kira.
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 1, "reason": "reacts"}))
    d = planner_agent.next_beat(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], locked_id="mei"
    )
    assert d.action == "speak" and d.actor_id == "kira"


def test_locked_pov_absent_from_prompt(client, db_session, monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], locked_id="mei")
    assert "Kira" in seen["user"] and "Mei" not in seen["user"]  # the POV char is off the roster


def test_only_pov_present_ends_without_llm(db_session):
    # Solo POV: the single cast member is the POV char → no one is selectable, the loop ends.
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [], locked_id="mei")
    assert d.action == "end"


def test_fallback_broadcast_skips_the_pov_character(db_session):
    # No LLM → fallback path; a whole-group direction walks only the NON-POV members.
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="broadcast", scope="all")
    assert planner_agent.next_beat(db_session, ctx, intent, [], [], locked_id="mei").actor_id == "kira"
    # Once Kira has spoken, the direction is satisfied — the POV char is never walked.
    assert (
        planner_agent.next_beat(db_session, ctx, intent, [], ["kira"], locked_id="mei").action == "end"
    )


def test_fallback_addressed_pov_is_not_selected(db_session):
    # Even if intent addresses the POV character (misclassification), the fallback never
    # picks them — the player is voicing that character, not the AI.
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="direct", addressed=["mei"])
    d = planner_agent.next_beat(db_session, ctx, intent, [], [], locked_id="mei")
    assert not (d.action == "speak" and d.actor_id == "mei")
