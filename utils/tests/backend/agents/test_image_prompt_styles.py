"""The four image-prompt agents write for the art style they are given.

No LLM call here — the system prompt *is* the unit of work. What matters is that the
chosen style's tags and model hint are present and the other two styles' are not, because
a prompt that names two looks produces neither.
"""

from __future__ import annotations

import pytest

from app.agents import character_agent, moment_agent, scenario_agent, setting_agent
from app.content import art_styles

# Which builder writes for which surface, and which tag field the style contributes.
BUILDERS = [
    ("character", character_agent._portrait_system, "portrait_tags"),
    ("setting", setting_agent._scene_art_system, "scene_tags"),
    ("scenario", scenario_agent._scene_art_system, "scene_tags"),
    ("moment", moment_agent._moment_system, "moment_tags"),
]

CASES = [
    pytest.param(name, build, field, style, id=f"{name}-{style.id}")
    for name, build, field in BUILDERS
    for style in art_styles.catalog()
]


@pytest.mark.parametrize("name,build,field,style", CASES)
def test_the_system_prompt_carries_the_chosen_style(name, build, field, style):
    prompt = build(style)
    assert getattr(style, field) in prompt
    assert style.model_hint in prompt


@pytest.mark.parametrize("name,build,field,style", CASES)
def test_the_system_prompt_names_no_other_style(name, build, field, style):
    prompt = build(style)
    for other in art_styles.catalog():
        if other.id == style.id:
            continue
        assert getattr(other, field) not in prompt


def test_a_photoreal_prompt_stops_telling_the_model_to_avoid_photorealism():
    """The pre-style wording pushed photorealism away in every render — the one thing a
    photoreal style cannot inherit."""
    prompt = character_agent._portrait_system(art_styles.PHOTOREAL)
    negative_line = next(line for line in prompt.splitlines() if line.startswith("negative:"))
    assert "photorealistic" not in negative_line
    assert "painting" in negative_line


def test_a_painted_prompt_still_avoids_photorealism():
    prompt = character_agent._portrait_system(art_styles.PAINTED)
    negative_line = next(line for line in prompt.splitlines() if line.startswith("negative:"))
    assert "photorealistic" in negative_line


@pytest.mark.parametrize("style", art_styles.catalog(), ids=lambda s: s.id)
def test_every_moment_prompt_still_asks_for_a_landscape_frame(style):
    assert art_styles.LANDSCAPE_TAG in moment_agent._moment_system(style)


@pytest.mark.parametrize("style", art_styles.catalog(), ids=lambda s: s.id)
def test_the_moment_fallback_negative_is_style_aware(style):
    negative = moment_agent._default_negative(style)
    assert moment_agent.BASE_NEGATIVE in negative
    assert style.negative_tags in negative


def test_moment_agent_still_exports_the_landscape_tag():
    """Callers and existing tests have always read it from here."""
    assert moment_agent.LANDSCAPE_TAG == art_styles.LANDSCAPE_TAG
