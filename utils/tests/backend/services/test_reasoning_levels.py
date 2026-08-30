"""Mapping the player-facing thinking level onto the backend's effort enum.

One function, three behaviours, and the third is the one that matters: an absent or
unrecognised level must stay absent rather than becoming a request. Every call site in the
turn loop has its own budget for a reason — the structured mode's prose call is ``NONE``
because it was measured spending 91 % of its output on hidden reasoning — and a control
that silently overrode those would undo the measurement.
"""

from __future__ import annotations

import pytest

from app.schemas.reasoning import THINKING_BUDGET, ReasoningEffort, effort_for_level


@pytest.mark.parametrize(
    ("level", "expected", "tokens"),
    [
        ("quick", ReasoningEffort.QUICK, 128),
        ("low", ReasoningEffort.LOW, 256),
        ("medium", ReasoningEffort.MEDIUM, 512),
        ("high", ReasoningEffort.HIGH, 1024),
        ("very_high", ReasoningEffort.VERY_HIGH, 2048),
        ("max", ReasoningEffort.MAX, 4096),
    ],
)
def test_the_six_levels_map_to_the_documented_budgets(level, expected, tokens):
    effort = effort_for_level(level)
    assert effort is expected
    assert THINKING_BUDGET[effort] == tokens


@pytest.mark.parametrize("value", [None, "", "   ", "enormous", "off"])
def test_anything_that_is_not_a_level_leaves_the_call_site_alone(value):
    assert effort_for_level(value) is None


def test_none_is_not_a_level_a_player_can_ask_for():
    """``ReasoningEffort.NONE`` is a call-site decision, not a rung on the player's ladder.

    Accepting it here would let a turn switch off deliberation the engine deliberately
    budgets for — the plan, for one, which is the only call in the structured mode that
    thinks at all.
    """
    assert effort_for_level("none") is None
