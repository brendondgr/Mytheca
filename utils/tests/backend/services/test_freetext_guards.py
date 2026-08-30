"""Which guards run on a passage that legitimately contains everybody.

Several of the structured engine's guards assume one speaker and are simply wrong here —
the cross-speaker check exists to catch one character writing another's lines, which in
free-text *is the format*. This module pins the selection, and the one new rule the mode
needed.
"""

from __future__ import annotations

import inspect

import pytest

from app.services import freetext_turn, prose_guards


# ---- the new rule ----------------------------------------------------------


def test_a_third_person_briefing_is_caught():
    briefing = (
        "Okay — the player wants Valdar to stonewall. Per the instruction, the cast list "
        "gives me Mei and Valdar, so the passage should open on her. Checking the voice "
        "sample for tone before writing the prompt response."
    )
    assert prose_guards.looks_like_briefing(briefing)


@pytest.mark.parametrize(
    "passage",
    [
        # Ordinary third-person prose, including the words that make the OTHER rule's
        # vocabulary list unsafe on its own: a heart beats, a doorway is blocked.
        "His heart beat hard against the block of stone at his back, and there was no "
        "response from the far side of the door. Mei counted three, then moved.",
        "The rain has found the gap in the shutters again, and Mei watches it darken the "
        'wood rather than look at him. "You are asking me the wrong thing," she says.',
        "",
    ],
)
def test_real_prose_is_not_a_briefing(passage):
    assert not prose_guards.looks_like_briefing(passage)


def test_it_takes_more_than_the_scratchpad_rule_does():
    """Deliberately stricter, because there is no second signal to lean on.

    `looks_like_scratchpad` gets away with two terms because it also requires the passage to
    have no first-person pronoun — a test a first-person character beat always fails and so
    exempts itself from. Third-person prose can never take that exemption.
    """
    two_terms = "The instruction was clear enough, and the roster said so."
    assert not prose_guards.looks_like_briefing(two_terms)


# ---- the selection ---------------------------------------------------------


def test_cross_speaker_speech_is_not_applied_to_a_free_text_body():
    """A body legitimately carries everyone's speech; the guard exists to catch the opposite.

    Asserted as a property of the module rather than of a run: `freetext_turn` must not
    reference the check at all, because a single call to it would silently truncate every
    passage in the mode at its second speaker.
    """
    source = inspect.getsource(freetext_turn)
    assert "cross_speaker" not in source


def test_the_second_person_check_is_gated_on_the_player_not_being_in_the_scene():
    """Under POV every "you" aimed at the player's character is correct."""
    source = inspect.getsource(freetext_turn._write)
    line = next(
        stripped
        for stripped in (l.strip() for l in source.splitlines())
        if "addresses_the_reader" in stripped
    )
    assert "pov is None" in line
