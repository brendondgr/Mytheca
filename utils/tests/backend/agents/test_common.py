"""Shared authoring-agent helpers — the reasoning/channel sanitizer (freeform prose)."""

from __future__ import annotations

from app.agents._common import strip_reasoning

# The exact reported narrator leak: a draft, a self-check, a revised draft, then the
# real final answer behind a stray ``<channel|>`` marker (see the play-experience plan).
_LEAKED = """The air thickens with the scent of musk and sulfur, the pheromones swirling around the two girls like a physical touch.

*Check:* 3 sentences? Yes. Third person? Yes. No dialogue? Yes.

*Revised:* The musky pheromones intensify, swirling around the girls like a physical touch.

<channel|> The musky pheromones intensify, swirling around the girls like a physical touch that makes their skin prickle and flush."""

_FINAL = (
    "The musky pheromones intensify, swirling around the girls like a physical touch "
    "that makes their skin prickle and flush."
)


def test_strip_reasoning_keeps_only_final_after_channel_marker():
    out = strip_reasoning(_LEAKED)
    assert out == _FINAL
    assert "*Check:*" not in out
    assert "*Revised:*" not in out
    assert "channel" not in out.lower()


def test_strip_reasoning_handles_harmony_channels_and_label():
    raw = (
        "<|channel|>analysis<|message|>The scene needs a beat of dread.<|end|>"
        "<|start|>assistant<|channel|>final<|message|>Rain hammers the tin roof."
    )
    assert strip_reasoning(raw) == "Rain hammers the tin roof."


def test_strip_reasoning_removes_paired_think_block():
    raw = "<think>I should be terse.</think>The lamps gutter out."
    assert strip_reasoning(raw) == "The lamps gutter out."


def test_strip_reasoning_passes_clean_prose_through():
    clean = "Kira's jaw tightens; the lamplight gutters."
    assert strip_reasoning(f"  {clean}  ") == clean


def test_strip_reasoning_does_not_touch_app_thinking_tag():
    # The app's own <thinking> tag (character emission) must survive — the scrub is for
    # freeform prose only and keys on <think> (deepseek) / harmony channels, not <thinking>.
    raw = "<thinking>plot</thinking> and speech"
    assert strip_reasoning(raw) == "<thinking>plot</thinking> and speech"


def test_strip_reasoning_empty_is_empty():
    assert strip_reasoning("") == ""
    assert strip_reasoning("   ") == ""
