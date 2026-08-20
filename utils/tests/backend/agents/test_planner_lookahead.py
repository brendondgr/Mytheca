"""`planner_agent.plan_beats` — several beats from ONE call.

The planner was 41 % of all turn time in EXP-2026-08-005 because it ran once per beat,
three to six times a turn. These tests pin the multi-beat contract, the shapes it must
tolerate from a model that ignores it, and the invariant that `lookahead=1` is byte-for-
byte the old behaviour so an operator with a customised planner prompt is unaffected.
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


def _patch(monkeypatch, content: str, seen: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        if seen is not None:
            body = json.loads(request.content.decode())
            seen.append(body["messages"][1]["content"])
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
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={}
        )
        for i in ids
    ]


def _ctx(cast) -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="pl1",
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


def test_a_beats_array_becomes_several_decisions(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"beats": [
        {"action": "narrate", "reason": "set it up", "register": "tense", "stakes": "the door"},
        {"action": "speak", "actor": 2, "addressing": 1, "reason": "reacts"},
        {"action": "end", "reason": "done"},
    ]}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=3
    )
    assert [b.action for b in beats] == ["narrate", "speak", "end"]
    assert beats[0].register == "tense" and beats[0].stakes == "the door"
    assert beats[1].actor_id == "kira" and beats[1].addressing_id == "mei"


def test_the_list_is_truncated_at_the_first_end(client, db_session, monkeypatch):
    """Beats planned after the turn stops describe a turn that will not happen."""
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"beats": [
        {"action": "speak", "actor": 1},
        {"action": "end"},
        {"action": "speak", "actor": 2},
    ]}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=5
    )
    assert [b.action for b in beats] == ["speak", "end"]


def test_lookahead_is_an_upper_bound_not_a_quota(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"beats": [
        {"action": "speak", "actor": 1}, {"action": "narrate"},
        {"action": "speak", "actor": 2}, {"action": "narrate"},
    ]}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=2
    )
    assert len(beats) == 2


def test_remaining_budget_clamps_the_lookahead(client, db_session, monkeypatch):
    """Never plan past the scene's own cap — those beats can never be run."""
    _configure_llm(client)
    seen: list[str] = []
    _patch(monkeypatch, json.dumps({"beats": [{"action": "speak", "actor": 1}]}), seen)
    planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [],
        lookahead=5, remaining_beats=2,
    )
    assert "Plan the next 2 beats" in seen[0]


def test_a_single_object_reply_still_works(client, db_session, monkeypatch):
    """A model that ignores the array contract must not break the turn."""
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 2}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=3
    )
    assert [b.action for b in beats] == ["speak"] and beats[0].actor_id == "kira"


def test_a_malformed_entry_truncates_rather_than_poisons(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"beats": [
        {"action": "speak", "actor": 1},
        {"action": "speak", "actor": 9},     # out of roster
        {"action": "narrate"},               # would have been fine, but order matters
    ]}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=3
    )
    assert [b.action for b in beats] == ["speak"] and beats[0].actor_id == "mei"


def test_an_all_malformed_reply_falls_back_to_one_beat(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"beats": [{"action": "nonsense"}]}))
    beats = planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=3
    )
    # freeform intent, nothing acted → the heuristic opens with the first cast member
    assert len(beats) == 1 and beats[0].actor_id == "mei"


def test_lookahead_one_asks_the_original_question(client, db_session, monkeypatch):
    """The single-beat prompt must not drift — operators can override this system prompt."""
    _configure_llm(client)
    seen: list[str] = []
    _patch(monkeypatch, json.dumps({"action": "end"}), seen)
    planner_agent.plan_beats(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], lookahead=1
    )
    assert seen[0].endswith("What is the next beat?")
    assert "beats" not in seen[0]


def test_next_beat_is_the_one_beat_wrapper(client, db_session, monkeypatch):
    _configure_llm(client)
    seen: list[str] = []
    _patch(monkeypatch, json.dumps({"action": "narrate"}), seen)
    decision = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [])
    assert decision.action == "narrate"
    assert seen[0].endswith("What is the next beat?")


def test_no_cast_ends_without_a_call(db_session):
    beats = planner_agent.plan_beats(db_session, _ctx([]), TurnIntent(), [], [], lookahead=3)
    assert len(beats) == 1 and beats[0].action == "end"
