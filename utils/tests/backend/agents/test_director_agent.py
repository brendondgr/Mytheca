"""Director agent — who's-up: fast paths, roster-constrained reasoned pick, fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import director_agent
from app.models import Scenario
from app.services import assembler, llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        return httpx.Response(404)  # engine probes → unknown

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
        assembler.CastMember(id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={}, recent_lines=[])
        for i in ids
    ]


def _ctx(cast, directed_at=None):
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id="e",
        directed_at=directed_at,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )


def test_directed_addressee_is_the_fast_path(db_session):
    d = director_agent.who_is_up(db_session, _ctx(_cast("mei", "kira"), directed_at="kira"))
    assert d.speakers == ["kira"] and d.needs_branch is False and d.beat == "addressed"


def test_solo_cast_fast_path(db_session):
    assert director_agent.who_is_up(db_session, _ctx(_cast("mei"))).speakers == ["mei"]


def test_no_cast_is_empty(db_session):
    assert director_agent.who_is_up(db_session, _ctx([])).speakers == []


def test_reasoned_pick_resolves_roster_numbers_in_order(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [2, 1], "needsBranch": True, "beat": "tension_spike"}))
    d = director_agent.who_is_up(db_session, _ctx(_cast("mei", "kira")))  # no addressee → escalate
    assert d.speakers == ["kira", "mei"]  # 2,1 → kira,mei
    assert d.needs_branch is True and d.beat == "tension_spike"


def test_reasoned_drops_out_of_roster_and_dedupes(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [9, 1, 2, 1], "needsBranch": False}))
    d = director_agent.who_is_up(db_session, _ctx(_cast("mei", "kira")))
    assert d.speakers == ["mei", "kira"]  # 9 dropped, 1 de-duped, order kept


def test_reasoned_caps_speakers(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [1, 2, 3, 4]}))
    d = director_agent.who_is_up(db_session, _ctx(_cast("a", "b", "c", "d")))
    assert len(d.speakers) == director_agent._MAX_SPEAKERS


def test_unconfigured_llm_falls_back_to_first(db_session):
    d = director_agent.who_is_up(db_session, _ctx(_cast("mei", "kira")))  # no LLM → fallback
    assert d.speakers == ["mei"] and d.beat == "fallback"


def test_malformed_director_reply_falls_back(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json at all")
    d = director_agent.who_is_up(db_session, _ctx(_cast("mei", "kira")))
    assert d.speakers == ["mei"] and d.beat == "fallback"


def test_propose_branches_parses_label_and_outcome(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps(
            {"choices": [{"label": "Back off", "outcome": "de-escalate"}, {"label": "Press her", "outcome": "escalate"}]}
        ),
    )
    branches = director_agent.propose_branches(db_session, _ctx(_cast("mei", "kira")), [])
    assert [b["label"] for b in branches] == ["Back off", "Press her"]
    assert branches[0]["outcome"] == "de-escalate"
    assert all("check" not in b for b in branches)  # no dice (D11)


def test_propose_branches_drops_empty_labels_and_caps(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"choices": [{"label": ""}, {"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}, {"label": "E"}]}),
    )
    branches = director_agent.propose_branches(db_session, _ctx(_cast("mei")), [])
    assert len(branches) == director_agent._MAX_BRANCHES
    assert all(b["label"] for b in branches)


def test_propose_branches_empty_when_unconfigured(db_session):
    assert director_agent.propose_branches(db_session, _ctx(_cast("mei")), []) == []


# ---- P10: mid-turn re-rank of the not-yet-spoken speakers ---------------------


def test_rerank_reorders_remaining_by_roster_number(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [3, 2]}))  # roster 3=jax, 2=kira
    out = director_agent.rerank(db_session, _ctx(_cast("mei", "kira", "jax")), ["kira", "jax"], [])
    assert out == ["jax", "kira"]


def test_rerank_drops_already_spoken_and_dedupes(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [1, 3, 3, 2]}))  # 1=mei already spoke
    out = director_agent.rerank(db_session, _ctx(_cast("mei", "kira", "jax")), ["kira", "jax"], [])
    assert out == ["jax", "kira"]  # mei dropped (not remaining), 3 de-duped, order 3,2


def test_rerank_preserves_omitted_remaining_at_tail(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"speakers": [3]}))  # model omits kira
    out = director_agent.rerank(db_session, _ctx(_cast("mei", "kira", "jax")), ["kira", "jax"], [])
    assert out == ["jax", "kira"]  # jax first (returned), kira kept (never silently dropped)


def test_rerank_single_remaining_skips_llm(db_session):
    # ≤1 remaining → nothing to re-rank; unchanged with no LLM configured.
    assert director_agent.rerank(db_session, _ctx(_cast("mei", "kira")), ["kira"], []) == ["kira"]


def test_rerank_unconfigured_llm_is_unchanged(db_session):
    out = director_agent.rerank(db_session, _ctx(_cast("mei", "kira", "jax")), ["kira", "jax"], [])
    assert out == ["kira", "jax"]  # no LLM → best-effort unchanged


def test_rerank_malformed_reply_is_unchanged(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json")
    out = director_agent.rerank(db_session, _ctx(_cast("mei", "kira", "jax")), ["kira", "jax"], [])
    assert out == ["kira", "jax"]
