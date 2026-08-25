"""Prompt registry — the single source of truth for the four writing agents' prompts."""

from __future__ import annotations

import pytest

from app.agents import (
    character_turn_agent,
    director_agent,
    narrator_agent,
    planner_agent,
    prompt_registry,
)

EXPECTED_KEYS = {
    "character.output_contract",
    "scene_script.system",
    "narrator.system",
    "narrator.system_long",
    "director.who_is_up",
    "director.rerank",
    "director.branch",
    "director.pov_branch",
    "planner.system",
    "ghostwriter.line",
    "recap.summarize",
}


def test_registry_covers_exactly_the_expected_keys():
    assert set(prompt_registry.keys()) == EXPECTED_KEYS
    # Every spec is fully populated (metadata drives the editor UI).
    for spec in prompt_registry.PROMPT_REGISTRY:
        assert spec.agent and spec.label and spec.description and spec.default.strip()


def test_agents_source_their_defaults_from_the_registry_no_drift():
    """The refactor moved text into the registry verbatim — assert no wording drift."""
    assert character_turn_agent._OUTPUT_CONTRACT == prompt_registry.default(
        prompt_registry.CHARACTER_OUTPUT_CONTRACT
    )
    assert narrator_agent._SYSTEM == prompt_registry.default(prompt_registry.NARRATOR_SYSTEM)
    assert narrator_agent._SYSTEM_LONG == prompt_registry.default(
        prompt_registry.NARRATOR_SYSTEM_LONG
    )
    assert director_agent._SYSTEM == prompt_registry.default(prompt_registry.DIRECTOR_WHO_IS_UP)
    assert director_agent._RERANK_SYSTEM == prompt_registry.default(prompt_registry.DIRECTOR_RERANK)
    assert director_agent._BRANCH_SYSTEM == prompt_registry.default(prompt_registry.DIRECTOR_BRANCH)
    assert director_agent._POV_BRANCH_SYSTEM == prompt_registry.default(
        prompt_registry.DIRECTOR_POV_BRANCH
    )
    assert planner_agent._SYSTEM == prompt_registry.default(prompt_registry.PLANNER_SYSTEM)


def test_default_raises_on_unknown_key():
    with pytest.raises(KeyError):
        prompt_registry.default("nope.missing")


def test_resolve_returns_defaults_with_no_layers():
    resolved = prompt_registry.resolve_prompts()
    assert resolved == {spec.key: spec.default for spec in prompt_registry.PROMPT_REGISTRY}


def test_resolve_layers_last_non_blank_wins():
    key = prompt_registry.NARRATOR_SYSTEM
    resolved = prompt_registry.resolve_prompts(
        {key: "GLOBAL"},  # global
        {key: "STORYLINE"},  # storyline beats global
        {key: "SCENARIO"},  # scenario beats storyline
    )
    assert resolved[key] == "SCENARIO"


def test_resolve_blank_and_none_inherit_the_layer_below():
    key = prompt_registry.PLANNER_SYSTEM
    resolved = prompt_registry.resolve_prompts(
        {key: "STORYLINE"},
        {key: "   "},  # blank scenario override → inherit storyline
        {key: None},  # None → inherit
    )
    assert resolved[key] == "STORYLINE"


def test_resolve_ignores_unknown_keys():
    resolved = prompt_registry.resolve_prompts({"bogus.key": "x"})
    assert "bogus.key" not in resolved
    assert set(resolved) == EXPECTED_KEYS


def test_the_two_dead_director_keys_are_hidden_from_the_catalog():
    """`planner_agent.plan_beats` makes the real per-beat decision; `who_is_up` and `rerank`
    are called only from their own unit tests. Offering them for editing would teach an
    author that editing prompts does nothing."""
    visible = {spec.key for spec in prompt_registry.visible_specs()}
    assert "director.who_is_up" not in visible
    assert "director.rerank" not in visible


def test_hidden_keys_are_still_registered_and_still_resolve():
    """Hidden, **not deleted** — they are the baseline arm of an open experiment
    (EXP-2026-08-001), and a stored override for one must neither disappear nor raise."""
    assert "director.who_is_up" in prompt_registry.keys()
    assert "director.rerank" in prompt_registry.keys()
    assert prompt_registry.default("director.who_is_up").strip()

    resolved = prompt_registry.resolve_prompts({"director.who_is_up": "Mine."})
    assert resolved["director.who_is_up"] == "Mine."


def test_every_visible_key_is_one_an_agent_reads():
    """The property the hiding exists to establish, stated as a list that must be justified
    rather than as a count that drifts."""
    consumed = {
        "character.output_contract",
        # Read by `scene_script_agent.build_prompt` — the whole-turn writer used when a scene
        # runs on continuous flow. Visible because an operator who has customised the
        # per-speaker contract will expect to customise this one too.
        "scene_script.system",
        "narrator.system",
        "narrator.system_long",
        "director.branch",
        "director.pov_branch",
        "planner.system",
        "ghostwriter.line",
        "recap.summarize",
    }
    assert {spec.key for spec in prompt_registry.visible_specs()} == consumed

