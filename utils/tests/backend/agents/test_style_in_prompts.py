"""Where the style guide lands in the actual prompts, and what that costs the cache.

The placement is the whole design: four blocks in a system message that is byte-identical
for every speaker and every beat of a scene, one clause in the volatile tail, and pacing in
the planner's system message only. Nothing else in the system would fail loudly if a block
drifted into the wrong region — it would just quietly cost cache on every beat, or quietly
never reach the model at all.
"""

from __future__ import annotations

from app.agents import character_turn_agent, planner_agent, prompt_registry
from app.content import style_presets
from app.models.scenario import Scenario
from app.services import assembler, style_guide

_ROMANCE = dict(style_presets.ROMANCE.blocks)


def _cast() -> list[assembler.CastMember]:
    return [
        assembler.CastMember(
            id="c_nadia", name="Nadia", role="a radiographer", traits="observant",
            speech="dry", color="#8A5A78", stats={},
        ),
        assembler.CastMember(
            id="c_emile", name="Emile", role="a joiner", traits="steady",
            speech="plain", color="#3A5A78", stats={},
        ),
    ]


def _ctx(storyline_blocks=None, scenario_blocks=None, **kw) -> assembler.TurnContext:
    cast = _cast()
    scenario = Scenario(storyline_id="s1", title="Scene", cast_ids=[m.id for m in cast])
    return assembler.TurnContext(
        scenario=scenario,
        session_id="ps1",
        storyline_id="s1",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer="A terrace house on a canal street.",
        stable_prefix=_prefix(storyline_blocks, scenario_blocks),
        style=style_guide.resolve(storyline_blocks, scenario_blocks),
        **kw,
    )


def _prefix(storyline_blocks=None, scenario_blocks=None) -> str:
    class _Storyline:
        title, genre = "Harrow Lane", "Contemporary"
        world_primer = "A terrace house on a canal street."
        premise = None

    return assembler._build_stable_prefix(
        _Storyline(), [], {}, style_guide.resolve(storyline_blocks, scenario_blocks)
    )


def _system(ctx: assembler.TurnContext) -> str:
    """The system message the character agent composes, exactly as it composes it."""
    contract = ctx.prompts.get(
        prompt_registry.CHARACTER_OUTPUT_CONTRACT,
        prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT),
    )
    return f"{contract}\n\n{ctx.stable_prefix}".strip()


def _user(ctx: assembler.TurnContext, speaker_index: int = 0, **kw) -> str:
    return character_turn_agent._build_user_prompt(
        ctx, ctx.cast[speaker_index], [], **kw
    )


# ---- the stable prefix ------------------------------------------------------------


def test_a_world_with_no_style_has_the_prefix_it_always_had():
    """The feature is optional; an un-styled world's bytes must not move."""
    assert _prefix(None, None) == _prefix({}, {})
    assert _prefix(None, None).startswith("WORLD: Harrow Lane")


def test_the_guide_sits_between_the_contract_and_the_world():
    system = _system(_ctx(_ROMANCE))
    guide_at = system.index("HOW THIS STORY IS WRITTEN")
    world_at = system.index("WORLD: Harrow Lane")
    contract_at = system.index("You are one character in a scene")
    assert contract_at < guide_at < world_at


def test_the_system_message_is_byte_identical_across_speakers_and_beats():
    """The cache claim, asserted rather than argued: nothing per-beat may reach the prefix."""
    ctx = _ctx(_ROMANCE)
    first = _system(ctx)
    # Same scene, a different speaker and a different beat's register/stakes.
    _user(ctx, 0, register="neutral", stakes="one thing")
    _user(ctx, 1, register="tense", stakes="another")
    assert _system(ctx) == first


def test_a_scenario_delta_only_changes_the_tail_of_the_system_message():
    """An override must break the cached prefix at its END, never in the middle of the guide."""
    plain = _system(_ctx(_ROMANCE))
    overridden = _system(_ctx(_ROMANCE, {"attention": "For this scene, write the cold."}))
    assert overridden != plain
    # Everything up to the delta is preserved verbatim, so only the appended bytes are lost.
    shared = 0
    for a, b in zip(plain, overridden):
        if a != b:
            break
        shared += 1
    assert shared > len(plain) * 0.75, "the delta broke the prefix too early to be worth caching"
    assert "For this scene, write the cold." in overridden


# ---- the volatile tail ------------------------------------------------------------


def test_the_signature_reaches_the_user_prompt_and_only_there():
    ctx = _ctx(_ROMANCE)
    user = _user(ctx, register="neutral")
    assert "Close and unsaid" in user
    assert "Close and unsaid" not in _system(ctx)


def test_the_signature_appears_exactly_once_per_beat():
    user = _user(_ctx(_ROMANCE), register="neutral")
    assert user.count("The style of this story, in one line:") == 1


def test_the_signature_is_fused_into_the_act_now_cue_at_the_registered_branch():
    """Both branches of the cue carry it — a register-less beat must not lose the style."""
    with_register = _user(_ctx(_ROMANCE), register="tense")
    without_register = _user(_ctx(_ROMANCE))
    assert "Close and unsaid" in with_register
    assert "Close and unsaid" in without_register


def test_no_signature_no_extra_text():
    ctx = _ctx({"voice": "Plain and short."})
    assert "The style of this story" not in _user(ctx, register="neutral")


def test_the_prose_prompt_never_carries_pacing():
    """Pacing is the planner's alone; in a prose prompt it would be instructions to nobody."""
    ctx = _ctx(_ROMANCE)
    pacing = _ROMANCE["pacing"]
    assert pacing not in _system(ctx)
    assert pacing not in _user(ctx, register="neutral")


# ---- the planner ------------------------------------------------------------------


def test_the_planner_system_carries_pacing_and_never_but_not_voice():
    system = planner_agent._planner_system(_ctx(_ROMANCE))
    assert _ROMANCE["pacing"] in system
    assert _ROMANCE["never"] in system
    assert _ROMANCE["voice"] not in system


def test_the_planner_system_is_unchanged_for_an_unstyled_world():
    ctx = _ctx(None)
    assert planner_agent._planner_system(ctx) == prompt_registry.default(
        prompt_registry.PLANNER_SYSTEM
    )


def test_pacing_is_appended_after_an_operator_override_not_woven_into_it():
    """A customised planner prompt must not be able to take the world's pacing with it."""
    ctx = _ctx(_ROMANCE)
    ctx.prompts[prompt_registry.PLANNER_SYSTEM] = "CUSTOM PLANNER PROMPT"
    system = planner_agent._planner_system(ctx)
    assert system.startswith("CUSTOM PLANNER PROMPT")
    assert _ROMANCE["pacing"] in system


# ---- assembly ---------------------------------------------------------------------


def test_assemble_context_resolves_both_layers_onto_the_context():
    from app.models.storyline import Storyline

    storyline = Storyline(id="s1", title="W", style_blocks={"voice": "Plain."})
    scenario = Scenario(storyline_id="s1", title="Scene", style_blocks={"voice": "Clipped."})
    resolved = style_guide.resolve_for(storyline, scenario)
    assert resolved.block("voice") == "Clipped."
