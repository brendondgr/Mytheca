"""A character never calls the person they are talking to "the player".

The character and narrator prompts used to label the human's line ``Player:`` — a production
label, not a name in anyone's world. In the EXP-2026-08-008 verification run **8 of 15
beats** referred to "the player" or "the player's": *"The player's question feels like a
stone dropped into a well…"*, *"I feel the player's gaze sweep over us"*, *"his eyes lock
onto the player"*. The prose was otherwise right — quoted speech, paragraphs, first person —
and the model reached for the only name its prompt gave that person.

Nothing caught it. ``looks_like_scratchpad`` cannot: it fires only on production vocabulary
**and** no first-person pronoun, and those passages say "I" throughout.
``starts_mid_sentence`` cannot: they open on a capital.

The fix is at the source — the line is labelled ``You:`` and both prompts say to write
*you* — so this guard is a backstop for the opening, plus the measurement the runner uses to
show the leak is gone rather than assert it.
"""

from __future__ import annotations

import pytest

from app.services import emission


@pytest.mark.parametrize(
    "passage",
    [
        "The player's question feels like a stone dropped into a well.",
        "The player asks about the ledger, and I have no answer ready.",
        "the player leans in, waiting.",
        "The Player's hand is still on the table.",
        "The player’s question hangs there.",
        "The user's request lands badly, and the room goes quiet.",
        # The live shapes, mid-passage — the common case, and why the default is whole-text.
        "I don't look at the door—not yet. I look at the player, seeing them lean in.",
        "I feel the player's gaze sweep over us, a cold, searching light.",
        "He doesn't look at the ledger; his eyes lock onto the player.",
    ],
)
def test_a_production_label_for_a_person_is_caught(passage: str) -> None:
    assert emission.names_the_player(passage) is True


@pytest.mark.parametrize(
    "passage",
    [
        # The same beats, written the way the contract now asks for.
        "Your question feels like a stone dropped into a well.",
        "The question feels like a stone dropped into a well.",
        "You ask about the ledger, and I have no answer ready.",
        "I feel your gaze sweep over us, a cold, searching light.",
        "He doesn't look at the ledger; his eyes lock onto you.",
        # "player" as an ordinary word in a world, which must survive.
        "The lute player has not looked up from his strings all evening.",
        "The other players fold, one after another, and leave me the pot.",
        "A player of some skill, they said, which was generous.",
        "",
    ],
)
def test_ordinary_prose_is_left_alone(passage: str) -> None:
    assert emission.names_the_player(passage) is False


def test_the_window_limits_it_to_an_opening() -> None:
    """The engine's gate judges an opening, so it passes a window; the metric does not.

    A long passage that reaches a card table on its fourth paragraph is not reading its own
    prompt, and the gate has already released its opening by then — so the windowed call
    must not fire on it, while the default whole-text call still reports it.
    """
    passage = "I close the ledger and look up. " * 40 + "The player to my left folds."
    assert len(passage) > emission.SCRATCHPAD_WINDOW
    assert emission.names_the_player(passage, window=emission.SCRATCHPAD_WINDOW) is False
    assert emission.names_the_player(passage) is True
