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


def _patch_llm_with_usage(monkeypatch, prompt_tokens: int | None):
    def handler(_req: httpx.Request) -> httpx.Response:
        payload: dict = {"choices": [{"message": {"content": _EMISSION}}]}
        if prompt_tokens is not None:
            payload["usage"] = {"prompt_tokens": prompt_tokens, "completion_tokens": 9}
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_generate_line_with_usage_surfaces_exact_prompt_tokens(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch_llm_with_usage(monkeypatch, 2048)
    ctx = _ctx()
    raw, prompt_tokens = character_turn_agent.generate_line_with_usage(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "I slide the pouch over.", "characterId": None}],
    )
    assert raw == _EMISSION
    assert prompt_tokens == 2048


def test_generate_line_with_usage_none_when_endpoint_omits_usage(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch_llm_with_usage(monkeypatch, None)
    ctx = _ctx()
    _, prompt_tokens = character_turn_agent.generate_line_with_usage(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    assert prompt_tokens is None


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
    # The carried-in stance is the only signal tracking how events actually changed this
    # character, so it lives in the recency TAIL beside the register — not in the HEAD,
    # where the voice-sample block outweighed it.
    assert "Guarded — I want the coin without the strings." in user
    assert "That is your condition now" in user
    assert "let <thinking> build on it in your own voice" in user
    assert "few words" not in user  # no longer clipped to a few words
    # Tail placement: after the transcript, and stated only once.
    assert user.index("Guarded — I want the coin") > user.index("Recent beats:")
    assert user.count("Guarded — I want the coin") == 1


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
    assert "do not come into this beat neutral" not in user
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
    # The recency tail must carry the "read the moment" cue so the character adapts its
    # manner instead of defaulting to habit.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "read the moment" in user
    assert "on autopilot" in user


def test_authored_atmosphere_is_scenery_not_the_present_moment(client, db_session, monkeypatch):
    # ``Setting.atmosphere`` is authored at world creation and never rewritten during play,
    # so it must never be asserted as the scene's CURRENT mood — doing so pinned every beat
    # to the world's opening tone. It still appears once, labelled as the place.
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
    assert "the scene right now" not in user
    # Present exactly once, as the authored place rather than a live report.
    assert user.count("a hushed, grieving funeral") == 1
    assert "Where this happens: Chapel — a hushed, grieving funeral" in user


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


def test_register_states_the_moment_as_fact_in_the_tail(client, db_session, monkeypatch):
    # The planner already read the moment for this beat, so the speaker is handed the
    # ANSWER, not the question — it should not have to out-argue its own voice samples.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="grave", stakes="the boy is bleeding out",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "The moment is GRAVE" in user
    assert "What is at stake right now: the boy is bleeding out." in user
    # The generic "work it out yourself" cue is replaced, not stacked on top of the answer.
    assert "Before you respond, read the moment" not in user
    # It lands in the recency tail, after the transcript.
    assert user.index("The moment is GRAVE") > user.index("Recent beats:")


def test_light_register_licenses_the_usual_manner(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="light",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "The moment is LIGHT" in user
    # No stakes given → no dangling stakes sentence.
    assert "What is at stake right now" not in user


def test_no_register_keeps_the_generic_cue(client, db_session, monkeypatch):
    # Planner fallback / puppet beat / a directly-built context: behave exactly as before.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "Before you respond, read the moment" in user
    assert "The moment is" not in user


_SAMPLE_ROWS = [
    {"situation": "haggling", "sample": "Coin first, favor later.", "moment": "light"},
    {"situation": "a friend bleeding out", "sample": "Stay with me. Stay.", "moment": "grave"},
]


def test_grave_beat_injects_only_the_grave_voice_sample(client, db_session, monkeypatch):
    # The voice samples are the highest-salience block in the prompt — showing the at-rest
    # quip on a grave beat is precisely what made characters unable to change register.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.cast[0].voice_sample_rows = _SAMPLE_ROWS
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="grave",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "Stay with me. Stay." in user
    assert "Coin first, favor later." not in user
    assert "how you sound in a moment like this one" in user


def test_registerless_beat_injects_every_sample_as_the_baseline(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.cast[0].voice_sample_rows = _SAMPLE_ROWS
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "Coin first, favor later." in user and "Stay with me. Stay." in user
    assert "your baseline voice" in user


def test_unmatched_register_keeps_the_whole_profile(client, db_session, monkeypatch):
    # A world authored before the field must never lose its voice profile.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.cast[0].voice_sample_rows = [{"situation": "haggling", "sample": "Coin first.", "moment": "light"}]
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="grave",
    )
    assert "Coin first." in json.loads(capture["body"])["messages"][1]["content"]


def _sampler(capture: dict) -> tuple[float, float, float]:
    body = json.loads(capture["body"])
    return body["top_p"], body["frequency_penalty"], body["presence_penalty"]


def test_grave_beat_damps_the_novelty_penalties(client, db_session, monkeypatch):
    # Frequency/presence penalties push the model toward unused tokens — toward flourish
    # and quips. A grave beat wants the plain, sincere, even repetitive word instead.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="grave",
    )
    top_p, frequency, presence = _sampler(capture)
    assert top_p == 0.85 and frequency == 0.20 and presence == 0.15


def test_light_beat_keeps_banter_varied(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="light",
    )
    top_p, frequency, presence = _sampler(capture)
    assert top_p == 0.95 and frequency == 0.45 and presence == 0.35


def test_registerless_beat_keeps_the_original_sampler(client, db_session, monkeypatch):
    # The no-register path must stay byte-identical to the pre-register behavior.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    assert _sampler(capture) == (0.92, 0.4, 0.3)
    # An unrecognized register lands on the same defaults rather than a partial update.
    capture.clear()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="apocalyptic",
    )
    assert _sampler(capture) == (0.92, 0.4, 0.3)


# ---- The scene direction (Narrator-Guided Scenes) --------------------------


def test_scene_direction_and_requirement_reach_the_prompt(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        scene_direction="the deal falls apart",
        requirements=["Mei walks away from the table"],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    # Where the scene is going is CONTEXT (middle); what this beat owes is the LAST thing
    # said, where recency attention is strongest.
    assert "Where this scene is going (the player's direction): the deal falls apart" in user
    assert "THIS BEAT MUST MAKE THIS TRUE: Mei walks away from the table" in user
    assert user.rstrip().endswith("never break character to acknowledge it.")


def test_the_requirement_is_an_outcome_not_a_script(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        requirements=["Mei walks away"],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "How you get there is yours" in user
    assert "Never quote or paraphrase the direction itself" in user


def test_several_requirements_are_joined(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        requirements=["Mei stands", "  ", "Mei draws"],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "THIS BEAT MUST MAKE THIS TRUE: Mei stands; Mei draws" in user  # blanks dropped


def test_no_direction_leaves_the_prompt_untouched(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "THIS BEAT MUST MAKE THIS TRUE" not in user
    assert "Where this scene is going" not in user


def test_a_requirement_composes_with_a_puppet_directive(client, db_session, monkeypatch):
    # A puppeted character can also be carrying a requirement — both tails are present, and
    # the requirement is last.
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        directive="tell Beth she is late",
        requirements=["Mei loses her temper"],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    assert "The player is directing you to: tell Beth she is late" in user
    assert user.index("THIS BEAT MUST MAKE THIS TRUE") > user.index("directing you to")


def test_contract_states_a_direction_is_what_not_how(client, db_session, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "It tells you WHAT, never HOW" in system


# ---- prompt layout vs. the inference server's prefix cache ------------------


def _user_message(capture: dict) -> str:
    body = json.loads(capture["body"])
    return next(m["content"] for m in body["messages"] if m["role"] == "user")


def test_the_system_message_is_byte_identical_across_turns(client, db_session, monkeypatch):
    """The cacheable region the design intends: it must not move between turns.

    If the system message varied — with the player's line, a stat, the transcript — the
    inference server could not reuse a single token of it and every call would re-read the
    whole world primer.
    """
    _configure_llm(client)
    ctx = _ctx()
    systems = []
    for beats in ([{"role": "player", "text": "turn one.", "characterId": None}],
                  [{"role": "player", "text": "a much later, different line.", "characterId": None}]):
        capture: dict = {}
        _patch_llm(monkeypatch, capture)
        ctx.recent_beats = beats
        character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], turn_beats=[])
        body = json.loads(capture["body"])
        systems.append(next(m["content"] for m in body["messages"] if m["role"] == "system"))

    assert systems[0] == systems[1]
    assert llm.prefix_cache_key(systems[0]) == llm.prefix_cache_key(systems[1])


def test_the_transcript_sits_AFTER_the_volatile_block(client, db_session, monkeypatch):
    """Characterisation test — this pins today's ordering, which costs the prompt cache.

    ``_build_user_prompt`` puts the speaker's CURRENT STAT VALUES in the HEAD, ahead of the
    transcript in the MIDDLE. A prefix cache can only reuse a common *prefix*, so a single
    stat change invalidates everything after it — including the entire conversation. The
    cost grows with the scene: the longer you play, the more is needlessly re-read.

    Measured in EXP-2026-08-005. If this assertion ever flips, the reordering has been
    done deliberately and the experiment's numbers should be re-taken.
    """
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.recent_beats = [{"role": "player", "text": "A LINE OF HISTORY.", "characterId": None}]
    character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], turn_beats=[])

    user = _user_message(capture)
    stats_at = user.find("trust")
    transcript_at = user.find("A LINE OF HISTORY.")
    assert stats_at != -1 and transcript_at != -1
    assert stats_at < transcript_at, (
        "volatile per-turn state now sits after the transcript — if that was intentional, "
        "re-run EXP-2026-08-005; the prompt-cache characteristic has changed."
    )
