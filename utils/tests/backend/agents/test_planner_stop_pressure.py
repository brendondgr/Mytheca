"""The planner is told how long the turn has already run, so it chooses to end.

Removing the player's `maxTurns` cap revealed that the planner almost never chose `end` on
its own — it had never had to, because the cap had always ended turns for it. Two live runs
on the same scene and the same direction produced **4 beats and 24**, the second stopping
only at the runaway backstop, which is not a turn anybody wants to sit through.

This is **pressure, not a limit**. The planner may still keep going when the scene genuinely
is not finished; what it can no longer do is keep going without being told what it has spent.
"""

from __future__ import annotations

import pytest

from app.agents.planner_agent import _PRESSURE_AFTER, _PRESSURE_HARD, _pressure


def test_a_short_turn_is_told_nothing_at_all():
    """Silence below the threshold, so an ordinary turn's prompt is byte-identical.

    That matters for more than tidiness: the planner's user message is what an inference
    server's prefix cache keys the turn on, and a line that changed every beat would cost
    reuse on every turn, including the short ones this is not aimed at.
    """
    for beats in range(_PRESSURE_AFTER):
        assert _pressure(beats) == ""


@pytest.mark.parametrize("beats", [_PRESSURE_AFTER, _PRESSURE_HARD - 1])
def test_a_long_turn_is_told_what_it_has_spent_and_who_is_waiting(beats):
    text = _pressure(beats)
    assert str(beats) in text
    assert "waiting" in text
    # It says end, and it says why not to when there is a reason — the point is a judgement,
    # not a stop.
    assert "End it unless" in text


@pytest.mark.parametrize("beats", [_PRESSURE_HARD, _PRESSURE_HARD + 20])
def test_a_very_long_turn_is_told_plainly_to_stop(beats):
    text = _pressure(beats)
    assert "END IT NOW" in text
    # And still not a hard stop: an outstanding requirement is delivered rather than dropped,
    # because the player asked for it and a turn that ends owing something is a lost request.
    assert "outstanding" in text


def test_it_never_becomes_a_cap():
    """No count here forbids a beat. Every message is a judgement the planner still makes."""
    for beats in (0, _PRESSURE_AFTER, _PRESSURE_HARD, 100):
        text = _pressure(beats)
        assert "you may not" not in text.lower()
        assert "maximum" not in text.lower()


def test_it_reaches_the_prompt_the_planner_actually_reads():
    """A pressure line nothing sends is a comment."""
    from app.agents import planner_agent

    import inspect

    source = inspect.getsource(planner_agent._plan_prompt)
    assert "_pressure(beats_so_far)" in source
