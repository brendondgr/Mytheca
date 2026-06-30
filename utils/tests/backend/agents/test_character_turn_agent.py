"""Character turn agent — bookended prompt assembly + emission passthrough (mocked LLM)."""

from __future__ import annotations

import json

import httpx

from app.agents import character_turn_agent
from app.models import Scenario
from app.services import assembler, llm

_EMISSION = '<speaker:1>\n<type:character_dialogue>\n"Coin\'s easy."'


def _patch_llm(monkeypatch, capture: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        capture["body"] = request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _ctx() -> assembler.TurnContext:
    mei = assembler.CastMember(
        id="c_mei",
        name="Mei",
        role="Cautious smuggler",
        traits="cautious, wary",
        speech="short, clipped lines",
        color="#3A5A78",
        stats={"trust": 38},
        recent_lines=["You always pay twice on these docks."],
    )
    scenario = Scenario(storyline_id="embergate", title="Standoff", cast_ids=["c_mei"], setting_id="")
    return assembler.TurnContext(
        scenario=scenario,
        session_id="ps1",
        storyline_id="embergate",
        directed_at="c_mei",
        cast=[mei],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[{"role": "player", "text": "I sat down.", "characterId": None}],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer="Embergate is a rain-soaked harbor city.",
        stable_prefix="WORLD PRIMER\nEmbergate is a rain-soaked harbor city.",
    )


def test_generate_line_returns_raw_emission(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    raw = character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], "I slide the pouch over.")
    assert raw == _EMISSION


def test_prompt_is_bookended_and_grounded(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], "I slide the pouch over.")

    body = json.loads(capture["body"])
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]

    # System carries the output contract + the cacheable stable prefix.
    assert "You voice exactly ONE character" in system
    assert "Embergate is a rain-soaked harbor city." in system

    # HEAD (primacy): identity + state + in-voice anchor at the front of the volatile block.
    assert user.startswith("You are [1] Mei")
    assert "short, clipped lines" in user
    assert "trust=38" in user
    assert "You always pay twice on these docks." in user
    # MIDDLE: roster + the player's current action.
    assert "I slide the pouch over." in user
    # TAIL (recency): act-now is last.
    assert user.rstrip().endswith("Emit only the tagged format.")
    assert "Respond now, in Mei's voice" in user
