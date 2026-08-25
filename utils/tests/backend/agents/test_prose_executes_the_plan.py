"""The writer executes the planned beat rather than re-deriving it.

The turn is planned once, at a full thinking budget, and the plan already states who speaks,
the register, what is at stake and **why this beat is here**. Before this, the last of those
was thrown away: `BeatDecision.reason` reached the Inspector trace and nothing else, so the
writer was told what was at risk but never what the beat was for — and was given 1024 private
thinking tokens to work it out again.

Measured on the live endpoint at that budget: 2646 reasoning characters for 247 characters of
prose. These tests pin the two halves of the trade — the intent arrives, and the private
deliberation does not.
"""

from __future__ import annotations

import json

import pytest

from app.agents import character_turn_agent
from app.schemas.reasoning import ReasoningEffort, budget_for

from .test_character_turn_agent import _configure_llm, _ctx, _patch_llm


def test_the_plans_reason_reaches_the_writer(client, db_session, monkeypatch):
    """The beat is told what it is for, in the recency tail where attention is strongest."""
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()

    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="tense",
        stakes="the deal collapses if he walks",
        purpose="make her admit she was there",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]

    assert "This beat is here to: make her admit she was there." in user
    assert "the deal collapses if he walks" in user


def test_a_beat_with_no_stated_purpose_says_nothing_about_one(
    client, db_session, monkeypatch
):
    """An empty reason must not become a dangling sentence in the prompt.

    Beats reach the writer from paths that never had a planner reason — the direction
    scheduler, a re-roll, a scripted fallback — and a prompt reading "This beat is here to: ."
    is noise the model has to interpret.
    """
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()

    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
        register="tense",
    )
    user = json.loads(capture["body"])["messages"][1]["content"]

    assert "This beat is here to" not in user


def test_the_writer_asks_for_no_private_deliberation(client, db_session, monkeypatch):
    """The other half of the trade, asserted on the wire rather than on a constant."""
    _configure_llm(client)
    capture: dict = {}
    _patch_llm(monkeypatch, capture)
    ctx = _ctx()

    character_turn_agent.generate_line(
        db_session, ctx, ctx.cast[0],
        turn_beats=[{"role": "player", "text": "x", "characterId": None}],
    )
    body = json.loads(capture["body"])

    assert character_turn_agent.TURN_EFFORT is ReasoningEffort.NONE
    assert budget_for(character_turn_agent.TURN_EFFORT) == 0
    # Both engine keys, because `apply_reasoning` sends whichever the backend uses and a 0
    # budget is what actually delivers "do not think" rather than a prompt asking nicely.
    assert body.get("thinking_token_budget") == 0
    assert body.get("thinking_budget_tokens") == 0


@pytest.mark.parametrize("guard", ["looks_like_scratchpad", "looks_degenerate"])
def test_the_guards_that_replaced_the_budget_still_exist(guard):
    """Dropping the private channel is only safe because these catch what it prevented.

    If either is ever removed, the reasoning behind `TURN_EFFORT = NONE` is gone with it and
    this test is the thing that says so.
    """
    from app.services import prose_guards

    assert callable(getattr(prose_guards, guard))
