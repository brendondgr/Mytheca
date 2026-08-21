"""The planner may stop and ask the player where the story goes — under the engine's terms.

The owner asked for this directly: "if more information is needed from the user as to what
direction they're going to take it, that it asks the user first and foremost". The risk is
the opposite failure — a planner that *can* ask will ask instead of doing its job — so the
permission is the caller's, the question may only be the turn's first beat, and a question
with nothing to ask is malformed rather than a blank prompt.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.agents.intent_agent import TurnIntent
from app.models import Scenario
from app.services import assembler, llm, llm_backend

ASK = {
    "action": "ask",
    "question": "Do you want to go after him, or let him go?",
    "options": ["Follow him", "Let him go"],
    "register": "tense",
    "stakes": "he is walking out with the ledger",
}


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str, seen: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        if seen is not None:
            seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _ctx() -> assembler.TurnContext:
    cast = [
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={}
        )
        for i in ("mei", "kira")
    ]
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


def test_the_question_and_its_options_survive_the_parse(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps(ASK))
    d = planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [], may_ask=True)
    assert d.action == "ask"
    assert d.question == "Do you want to go after him, or let him go?"
    assert d.options == ["Follow him", "Let him go"]
    assert d.register == "tense"  # the read of the moment rides on every action


def test_an_ask_the_caller_did_not_allow_is_dropped(client, db_session, monkeypatch):
    """The permission is the engine's: it knows whether anything has happened yet."""
    _configure_llm(client)
    _patch(monkeypatch, json.dumps(ASK))
    d = planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [])
    assert d.action != "ask"  # falls back to a real beat rather than a question nobody delivers


def test_the_contract_only_reaches_the_prompt_when_asking_is_allowed(
    client, db_session, monkeypatch
):
    """Prompt bytes are prefix-cache-sensitive; the common path must not carry dead text."""
    _configure_llm(client)
    seen: dict = {}
    _patch(monkeypatch, json.dumps({"action": "end"}), seen)
    planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [])
    assert '"action": "ask"' not in seen["user"]
    planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [], may_ask=True)
    assert '"action": "ask"' in seen["user"]


def test_an_ask_with_no_question_is_malformed(client, db_session, monkeypatch):
    """A blank question would render as an empty prompt with no way to answer it."""
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "ask", "options": ["a", "b"]}))
    d = planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [], may_ask=True)
    assert d.action != "ask"


def test_a_question_with_no_options_is_still_a_question(client, db_session, monkeypatch):
    """The player can always answer in the composer — the options are a convenience."""
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "ask", "question": "Where to?"}))
    d = planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [], may_ask=True)
    assert d.action == "ask" and d.question == "Where to?" and d.options == []


def test_options_are_bounded(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"action": "ask", "question": "Which?", "options": list("abcdefgh")}),
    )
    d = planner_agent.next_beat(db_session, _ctx(), TurnIntent(), [], [], may_ask=True)
    assert len(d.options) == planner_agent._MAX_ASK_OPTIONS


def test_a_question_planned_after_a_beat_is_dropped_with_everything_after_it(
    client, db_session, monkeypatch
):
    """A question that arrives once the scene has moved is answering nothing."""
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"beats": [{"action": "narrate", "reason": "set it up"}, ASK,
                              {"action": "speak", "actor": 1, "reason": "after"}]}),
    )
    beats = planner_agent.plan_beats(
        db_session, _ctx(), TurnIntent(), [], [], lookahead=3, may_ask=True
    )
    assert [b.action for b in beats] == ["narrate"]


def test_a_question_stops_the_plan_there(client, db_session, monkeypatch):
    """Nothing planned past the question still applies — the answer decides what follows."""
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"beats": [ASK, {"action": "speak", "actor": 1, "reason": "after"}]}),
    )
    beats = planner_agent.plan_beats(
        db_session, _ctx(), TurnIntent(), [], [], lookahead=3, may_ask=True
    )
    assert [b.action for b in beats] == ["ask"]
