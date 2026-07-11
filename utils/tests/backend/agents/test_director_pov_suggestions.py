"""Director — Player-POV follow-up lines (`propose_pov_lines`).

Under Player POV the end-of-turn suggestions must read like something the POV character
would SAY next (first-person, in-voice), not a situation-wide narrator fork — they flow
into the composer as the player's own next line. Same `{label, outcome}` shape + count
clamp as `propose_branches`, so the client's choose→composer path is unchanged.
"""

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
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _cast(*ids: str) -> list[assembler.CastMember]:
    return [
        assembler.CastMember(
            id=i, name=i.title(), role="Barkeep", traits="", speech="clipped, dry",
            color="#000", stats={}, recent_lines=[], voice_samples="Sample: 'Coin first.'",
            disposition="wary",
        )
        for i in ids
    ]


def _ctx(cast):
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


def _speaker(cast, cid):
    return next(c for c in cast if c.id == cid)


def test_pov_lines_parse_label_and_outcome(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps(
            {
                "choices": [
                    {"label": "You already know my answer.", "outcome": "press"},
                    {"label": "Fine. What's it worth to you?", "outcome": "probe"},
                ]
            }
        ),
    )
    cast = _cast("mei", "kira")
    lines = director_agent.propose_pov_lines(db_session, _ctx(cast), [], _speaker(cast, "mei"))
    assert [c["label"] for c in lines] == ["You already know my answer.", "Fine. What's it worth to you?"]
    assert lines[0]["outcome"] == "press"


def test_pov_lines_count_caps_and_drops_empty(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"choices": [{"label": "One."}, {"label": "  "}, {"label": "Two."}, {"label": "Three."}]}),
    )
    cast = _cast("mei")
    lines = director_agent.propose_pov_lines(db_session, _ctx(cast), [], _speaker(cast, "mei"), count=2)
    assert [c["label"] for c in lines] == ["One.", "Two."]  # empty dropped, capped at 2


def test_pov_lines_count_zero_disables_no_llm_call(client, db_session, monkeypatch):
    def handler(_req: httpx.Request) -> httpx.Response:  # any call would blow up the test
        raise AssertionError("no LLM call expected when count=0")

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    cast = _cast("mei")
    assert director_agent.propose_pov_lines(db_session, _ctx(cast), [], _speaker(cast, "mei"), count=0) == []


def test_pov_lines_empty_when_unconfigured(db_session):
    cast = _cast("mei")
    assert director_agent.propose_pov_lines(db_session, _ctx(cast), [], _speaker(cast, "mei")) == []


def test_pov_prompt_is_first_person_in_the_characters_voice(client, db_session, monkeypatch):
    # The prompt names the POV character, folds in their voice/manner, and asks for
    # first-person lines THEY might say — the whole point of the POV suggestion path.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        seen["system"] = body["messages"][0]["content"]
        seen["user"] = body["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"choices": []})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    cast = _cast("mei", "kira")
    beats = [{"role": "character", "text": "The coin is on the table.", "characterId": "kira"}]
    director_agent.propose_pov_lines(db_session, _ctx(cast), beats, _speaker(cast, "mei"), count=3)

    system, user = seen["system"], seen["user"]
    assert "first-person" in system.lower() and "voice" in system.lower()
    assert "speaking AS this character" in user and "Mei" in user
    assert "clipped, dry" in user or "Coin first" in user  # the character's voice is folded in
    assert "The coin is on the table." in user  # anchored to the latest beat
