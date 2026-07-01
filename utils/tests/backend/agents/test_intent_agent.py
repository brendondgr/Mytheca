"""Input-intent interpreter — kind/actors/addressed parse, roster-constrained, fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import intent_agent
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


def test_puppet_splits_actor_from_target(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps(
            {
                "kind": "puppet",
                "actors": [1],
                "addressed": [2],
                "scope": "some",
                "directive": "Beth tells Mei she hates her",
            }
        ),
    )
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth", "mei")), "Beth tells Mei 'I hate you'")
    assert intent.kind == "puppet"
    assert intent.directed_actors == ["beth"]  # the one being puppeted
    assert intent.addressed == ["mei"]  # the target reacts
    assert intent.directive


def test_direct_has_target_no_actor(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"kind": "direct", "actors": [], "addressed": [2]}))
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth", "mei")), "I glare at Mei")
    assert intent.kind == "direct" and intent.directed_actors == [] and intent.addressed == ["mei"]


def test_broadcast_sets_scope_all(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"kind": "broadcast", "scope": "all"}))
    intent = intent_agent.interpret(db_session, _ctx(_cast("a", "b", "c")), "everyone introduces themselves")
    assert intent.kind == "broadcast" and intent.scope == "all"


def test_out_of_roster_numbers_dropped(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"kind": "puppet", "actors": [9, 1], "addressed": [7]}))
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth", "mei")), "x")
    assert intent.directed_actors == ["beth"]  # 9 dropped, 1→beth
    assert intent.addressed == []  # 7 dropped


def test_unknown_kind_falls_back_to_freeform(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"kind": "gibberish", "directive": "do a thing"}))
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth")), "do a thing")
    assert intent.kind == "freeform" and intent.directive == "do a thing"


def test_malformed_reply_is_freeform(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json at all")
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth", "mei")), "hello there")
    assert intent.kind == "freeform" and intent.directive == "hello there"


def test_unconfigured_llm_is_freeform(db_session):
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth")), "hello")
    assert intent.kind == "freeform" and intent.directive == "hello"
