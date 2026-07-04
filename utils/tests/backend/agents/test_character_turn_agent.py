"""Character turn agent — bookended prompt assembly + emission passthrough (mocked LLM)."""

from __future__ import annotations

import json

import httpx

from app.agents import character_turn_agent
from app.models import Scenario
from app.models.stat import StatDefinition
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


def test_stat_defs_inject_current_band_named_to_the_character(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()  # speaker Mei has stats={"trust": 38}
    ctx.stat_defs = [
        StatDefinition(
            key="trust",
            display_name="Trust",
            min=0,
            max=100,
            default=50,
            description="{Character}'s faith in the people around them.",
            bands=[
                {"min": 0, "max": 20, "label": "Wary", "description": "{Character} trusts no one."},
                {"min": 21, "max": 60, "label": "Guarded", "description": "{Character} keeps their guard up."},
            ],
        )
    ]
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "I slide the pouch over.", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]

    # The value (38) falls in the Guarded band → its label + description, name-substituted.
    assert "Trust 38/100 (Guarded)" in user
    assert "Mei keeps their guard up." in user
    assert "Mei's faith in the people around them." in user  # general description too
    # The non-current band's text is NOT shown, and no placeholder leaks.
    assert "trusts no one" not in user
    assert "{Character}" not in user
    # The old flat "trust=38" form is replaced by the enriched block.
    assert "trust=38" not in user


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


def test_interior_disposition_injected_and_builds_thinking(client, db_session, monkeypatch):
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
    # HEAD carries the carried-in stance; TAIL has the thought BUILD on it (not clip it).
    assert "Your current inner stance: Guarded — I want the coin without the strings." in user
    assert "let <thinking> build on it in your own voice" in user
    assert "few words" not in user  # no longer clipped to a few words


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
    assert "let <thinking> build on it" not in user


def test_thinking_contract_asks_for_a_fuller_in_voice_paragraph(client, db_session, monkeypatch):
    # The <thinking> step is now a real in-voice deliberation (a short paragraph), and the
    # turn runs at MEDIUM effort so the model has room to reason before speaking.
    from app.schemas.reasoning import ReasoningEffort

    assert character_turn_agent.TURN_EFFORT == ReasoningEffort.MEDIUM
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "short paragraph" in system
    assert "one or two clipped sentences" not in system.lower()


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
    # Voice samples sit in the HEAD (primacy) as a baseline, not a script — the register is
    # allowed to flex with the moment rather than being locked to the samples.
    assert "Voice samples — your baseline voice" in user
    assert "let the register flex with the moment" in user
    assert 'When haggling: "Coin first, favor later."' in user


def test_tail_surfaces_read_the_moment_adaptation_cue(client, db_session, monkeypatch):
    # The recency tail must carry the "read the moment" cue and surface the scene's mood as a
    # tonal constraint, so the character adapts its manner instead of defaulting to habit.
    from app.models import Setting

    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.setting = Setting(name="Chapel", atmosphere="a hushed, grieving funeral")
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "read the moment" in user
    assert "on autopilot" in user
    # The mood is restated inside the tail cue (not just as middle scenery).
    assert "the scene right now: a hushed, grieving funeral" in user


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
    # The (character-agnostic) thinking rule steers the hidden thought into voice too — but
    # the voice's register bends with the stakes rather than being locked to the samples.
    assert "same underlying person as your speech style and voice samples" in system
    assert "BEND WITH THE STAKES" in system


def test_contract_grants_situational_manner_adaptation(client, db_session, monkeypatch):
    # Personality is constant, manner adapts: the contract must tell the character to read the
    # moment and drop the habitual act when the situation turns grave (the core fix).
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "personality is CONSTANT" in system and "MANNER adapts" in system
    assert "on autopilot" in system
    # The <thinking> step appraises the moment BEFORE reasoning toward a response.
    assert "FIRST read the moment" in system


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


def test_transcript_window_follows_context_beats(client, db_session, monkeypatch):
    # The rendered transcript depth is the scene's context_beats (not a fixed 14): with
    # context_beats=5 over 10 prior beats + the player line, only the newest 5 appear.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.context_beats = 5
    ctx.recent_beats = [{"role": "narrator", "text": f"beat{i}", "characterId": None} for i in range(10)]
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "myturn", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    # combined [beat0..beat9, myturn] sliced to the last 5 → beat6..beat9 + myturn.
    assert "beat9" in user and "beat6" in user and "myturn" in user
    assert "beat5" not in user and "beat0" not in user


def test_dialogue_is_optional_but_thinking_is_always_required(client, db_session, monkeypatch):
    # Fix for over-talking: the character ALWAYS thinks, but a spoken line is optional — in
    # action moments they may act or think without talking.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "character_dialogue is OPTIONAL" in system
    assert "ALWAYS required" in system  # <thinking> stays mandatory every beat
    assert "over-talking" in system
    assert "action-only" in system and "thinking-only" in system
