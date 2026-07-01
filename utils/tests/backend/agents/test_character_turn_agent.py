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
    raw = character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "I slide the pouch over.", "characterId": None}],
    )
    assert raw == _EMISSION


def test_prompt_is_bookended_and_grounded(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "I slide the pouch over.", "characterId": None}],
    )

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


def test_retrieved_lore_is_injected_into_the_prompt(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.retrieved_lore = "\n\nRETRIEVED LORE:\n- the Ashford fire: a smuggling deal gone wrong."
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "Tell me about the Ashford fire.", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "the Ashford fire: a smuggling deal gone wrong." in user


def test_prompt_requests_a_hidden_thinking_block(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "<thinking>" in system and "never shown" in system


def test_interior_disposition_injected_and_shortens_thinking(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.cast[0].disposition = "Guarded — I want the coin without the strings."
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    # HEAD carries the carried-in stance; TAIL nudges a shorter hidden thinking block.
    assert "Your current inner stance: Guarded — I want the coin without the strings." in user
    assert "keep <thinking> to a few words" in user


def test_no_disposition_omits_inner_stance(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()  # no disposition set
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "current inner stance" not in user
    assert "keep <thinking> to a few words" not in user


def test_relationship_note_injected_into_prompt(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        relationship_note="You fear Beth (old debt). You and Beth are both connected to Cy.",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "Your ties in this scene: You fear Beth (old debt)." in user


def test_voice_samples_injected_into_head(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.cast[0].voice_samples = '- When haggling: "Coin first, favor later."'
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    # Voice samples sit in the HEAD (primacy), anchoring both speech and thought.
    assert "Voice samples — how you sound" in user
    assert 'When haggling: "Coin first, favor later."' in user


def test_no_voice_samples_omits_the_block(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()  # no voice_samples set (default "")
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "Voice samples" not in user


def test_thinking_contract_anchors_to_voice(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    # The (character-agnostic) thinking rule steers the hidden thought into voice too.
    assert "SAME voice as your speech style and voice samples" in system


def test_voice_sampler_tuning_applied(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    body = json.loads(capture["body"])
    assert body["top_p"] == 0.92
    assert body["frequency_penalty"] == 0.4
    assert body["presence_penalty"] == 0.3
