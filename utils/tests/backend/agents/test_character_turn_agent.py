"""Character turn agent — stable→transcript→volatile prompt assembly + emission passthrough."""

from __future__ import annotations

import json
import os

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


def test_prompt_is_ordered_stable_first_and_grounded(client, db_session, monkeypatch):
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

    # STABLE region leads: the scene as authored, identical for every speaker and turn.
    assert user.startswith("Where this happens:") or user.startswith("Cast in the scene:")
    # Everything volatile is still present — it has moved, not gone.
    assert "short, clipped lines" in user
    assert "trust=38" in user
    assert "You always pay twice on these docks." in user
    assert "You are [1] Mei" in user
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
    # The block is still requested and still the character's own private voice; it is now
    # asked to be brief, and it is the ONLY deliberation the turn pays for.
    assert "<thinking>" in system
    assert "in your character's own voice" in system


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


def test_the_character_deliberates_once_in_voice_and_not_again_in_hidden_reasoning(
    client, db_session, monkeypatch
):
    """One deliberation, not two.

    The character already thinks *in the output* — the visible in-voice ``<thinking>``
    block the player reads. Letting the model also fill a hidden reasoning channel first
    means it works the same beat through twice and the player waits through both, while
    only the second is ever shown. EXP-2026-08-006 measured that beat at ~35 s to its
    thought and ~10 s more to its line, the largest single cost in a turn.
    """
    from app.schemas.reasoning import ReasoningEffort

    assert character_turn_agent.TURN_EFFORT == ReasoningEffort.NONE
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    body = json.loads(capture["body"])
    system = body["messages"][0]["content"]
    # The visible thought survives, and is asked to be brief rather than an essay.
    assert "<thinking>" in system
    assert "ONE or TWO sentences" in system
    assert "short paragraph" not in system
    # The hidden channel is switched off by the budget key alone — measured on the
    # deployed route, a 0 budget yields 0 reasoning characters. Forcing the chat
    # template's own `enable_thinking` flag off as well was tried and rejected: it
    # suppressed nothing extra and made the model terser.
    assert body.get("thinking_token_budget") == 0
    assert "chat_template_kwargs" not in body


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
    assert "Read the moment as it actually stands" in system


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


def test_transcript_window_follows_context_beats_plus_one_anchor_block(
    client, db_session, monkeypatch
):
    """The depth is the scene's ``context_beats`` plus room for one anchor block.

    ``recent_beats`` arrives block-anchored from the assembler, holding between
    ``context_beats`` and ``context_beats + block`` beats; that overshoot is exactly what
    keeps the transcript's first line still between re-anchors. Re-trimming to
    ``context_beats`` here would slide it by one beat per turn and throw the prompt cache
    away again — so the cap allows the block, and only clips beyond it.
    """
    from app.core.config import get_settings

    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    block = get_settings().turn_transcript_anchor_block
    ctx = _ctx()
    ctx.context_beats = 5
    total = 5 + block + 10  # comfortably past the cap
    ctx.recent_beats = [
        {"role": "narrator", "text": f"beat{i}", "characterId": None} for i in range(total)
    ]
    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "myturn", "characterId": None}],
    )
    user = json.loads(capture["body"])["messages"][1]["content"]
    kept = 5 + block  # + the player line
    assert "myturn" in user
    assert f"beat{total - 1}" in user                     # newest kept
    assert f"beat{total - kept + 1}" in user              # inside the window
    assert f"beat{total - kept - 1}" not in user          # clipped
    assert "beat0" not in user


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


def test_the_transcript_sits_BEFORE_everything_volatile(client, db_session, monkeypatch):
    """The prompt-cache invariant, stated as an assertion.

    A prefix cache matches from the first token and stops at the first byte that differs.
    ``_build_user_prompt`` used to put the speaker's CURRENT STAT VALUES in the HEAD, ahead
    of the transcript — so a single stat change invalidated everything after it, including
    the whole conversation. EXP-2026-08-005 measured the result: cached tokens pinned at
    exactly 800 (the system message) on all ten turns of a scene while the prompt grew
    1830 → 4678.

    Now the order is stable → transcript → volatile. If this assertion ever flips, the
    reusable prefix has collapsed back to the system message and the reordering has been
    undone — re-run EXP-2026-08-006 before accepting it.
    """
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.recent_beats = [{"role": "player", "text": "A LINE OF HISTORY.", "characterId": None}]
    character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], turn_beats=[])

    user = _user_message(capture)
    transcript_at = user.find("A LINE OF HISTORY.")
    assert transcript_at != -1
    for volatile in ("trust", "You are [1] Mei", "Respond now, in Mei's voice"):
        at = user.find(volatile)
        assert at != -1, volatile
        assert at > transcript_at, (
            f"{volatile!r} now sits above the transcript — every token after it is "
            "re-read on every call. If that was intentional, re-run EXP-2026-08-006."
        )


def test_the_stable_region_is_identical_for_every_speaker(client, db_session, monkeypatch):
    """Two speakers in one turn must share a prefix, or the cache cannot span a turn."""
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()
    ctx.recent_beats = [{"role": "player", "text": "A LINE OF HISTORY.", "characterId": None}]

    prompts = []
    for member in ctx.cast[:2]:
        character_turn_agent.generate_line(db_session, ctx, member, turn_beats=[])
        prompts.append(_user_message(capture))
    if len(prompts) < 2:
        return  # single-cast fixture — nothing to compare
    shared = os.path.commonprefix(prompts)
    assert "Cast in the scene:" in shared
    assert "A LINE OF HISTORY." in shared  # the transcript is shared too, not just the header
