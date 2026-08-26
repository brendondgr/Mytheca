"""A beat belongs to ONE person — including their inner life.

`cross_speaker_speech` catches a beat that puts words in another character's mouth. It passed
clean on a live beat that never quoted anybody and still narrated two other characters'
private thoughts: *"he understands that he has a sentence in his throat"*, *"the blink is the
sound of a decision reaching the back of her skull"*.

That is the same defect wearing a quieter coat. Once one character may narrate another's
interior, the scene stops being a room with several people in it and becomes one omniscient
voice wearing their names — which is what the per-speaker architecture pays N model calls to
avoid.
"""

from __future__ import annotations

import pytest

from app.services import prose_guards

OTHERS = ["Zoe", "Aldous"]


@pytest.mark.parametrize(
    "text",
    [
        "Zoe realised the debt was never going to be paid.",
        "Aldous had never really understood what the ledger cost her.",
        "Zoe's decision arrived somewhere behind her eyes.",
        "Aldous remembered the harbour, and the smell of it.",
        "Zoe wanted to say something and did not.",
    ],
)
def test_another_characters_interior_is_caught(text):
    assert prose_guards.narrates_another_mind(text, others=OTHERS) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Observable from outside — a speaker can SEE these. This is the line the guard draws.
        "Zoe frowned and put the glass down.",
        "Aldous stood, tall enough to block the light.",
        "Zoe's hand stopped halfway to the ledger.",
        "Zoe looked at the candle over my shoulder.",
        # My own interior is the whole point of a character beat.
        "I realised the argument had stopped, and I knew what that meant.",
        # Quoted speech is stripped first: a character may SAY "you knew".
        'I leaned in. "You knew, Zoe. You decided this weeks ago."',
        "",
    ],
)
def test_what_a_speaker_can_legitimately_write_is_left_alone(text):
    assert prose_guards.narrates_another_mind(text, others=OTHERS) is None


def test_pronoun_interiority_is_a_known_gap_not_an_accident():
    """The exact sentence from the live beat that motivated this guard — and it PASSES.

    Pinned so the limitation is a recorded decision rather than a surprise: naming who "he"
    is needs coreference resolution, and a wrong guess cuts correct prose mid-beat. If this
    ever starts failing because someone taught the guard pronouns, that is an improvement and
    the test should be updated deliberately, with false positives measured first.
    """
    text = "He understands that he has a sentence in his throat, and he does not close it."
    assert prose_guards.narrates_another_mind(text, others=OTHERS) is None


def test_a_narrator_beat_is_not_this_guards_business():
    """The narrator is allowed to be omniscient; a CHARACTER is not.

    The guard takes the list of others from the caller, so a narration beat simply passes an
    empty list. Pinned so nobody wires it into the narrator path by symmetry.
    """
    text = "Zoe realised the debt was never going to be paid."
    assert prose_guards.narrates_another_mind(text, others=[]) is None
