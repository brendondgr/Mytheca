"""A collapsed generation is cut; a long one is not.

The passage form deliberately has **no length cap** — a character may hold the floor for
as long as the moment needs, and it streams, so length costs the reader nothing. That only
works if a generation which has stopped producing language is caught some other way. Two
live runs produced beats of 29,660 and 48,167 characters that opened as ordinary prose,
drifted into the model's own notes, and ended in "Rex Rex Rex …" and "AT AT AT AAAA".
"""

from __future__ import annotations

from app.services.emission import looks_degenerate

GOOD = (
    "The rain has found the gap in the shutters again, and I watch it darken the wood "
    "rather than look at him. His question is still sitting there and I let it sit, "
    "because an answer given too quickly is a confession. I turn the cup a half-turn on "
    "the table so my hands have something to do while the silence works on him."
)


def test_ordinary_prose_is_not_flagged():
    assert looks_degenerate(GOOD) is False


def test_a_long_passage_is_not_flagged_for_being_long():
    """Length is explicitly not the signal — the owner asked for no cap."""
    assert looks_degenerate(GOOD * 40) is False


def test_a_deliberately_repetitive_line_is_not_flagged():
    """People write incantation and insistence; that is prose, not collapse."""
    text = (
        "I will not. I will not. I will not go back to that house, not for him, not for "
        "the ledger, not for any coin he can put on this table tonight or any other."
    )
    assert looks_degenerate(text) is False


def test_a_token_loop_is_flagged():
    assert looks_degenerate("AT " * 90) is True
    assert looks_degenerate("Rex " * 80) is True


def test_only_the_tail_matters_so_a_beat_that_collapses_late_is_caught():
    """The observed shape: good prose first, collapse at the end."""
    assert looks_degenerate(GOOD + " " + "AAAA " * 90) is True


def test_a_word_salad_is_flagged_even_though_every_word_differs():
    """The second observed mode, which the variety check alone cannot see.

    A live beat drifted into an unrelated geology word list — every word distinct, so
    lexical variety stayed high while the language was gone. What it had lost was sentence
    structure: seventy words without a mark of punctuation.
    """
    salad = (
        "mineral weathered transported deposited sediment erosion weathering transport "
        "deposition compaction lithification metamorphism igneous intrusive extrusive "
        "volcanic lava magma plutonic dike sill batholith stock laccolite lopolite "
        "kimberlite xenolith xenocryst inclusion bubble vesicle porosity permeability"
    )
    assert looks_degenerate(salad) is True


def test_unpunctuated_prose_is_not_flagged_when_it_is_still_a_sentence():
    """One comma in seventy words is enough — the rule is deliberately conservative."""
    text = (
        "I walk out into the rain and I do not look back at the house or the light in "
        "the window or the shape of him standing in it and I keep walking until the "
        "road turns and the noise of the place is gone behind me, finally"
    )
    assert looks_degenerate(text) is False


def test_a_short_string_is_never_flagged():
    """Too little text to judge — never guess on a fragment."""
    assert looks_degenerate("Rex Rex Rex") is False
    assert looks_degenerate("") is False


def test_the_runaway_stop_is_far_beyond_any_honest_passage():
    """The hard stop protects the endpoint, and must never be reached by writing.

    A live run produced ONE generation of 48,000 completion tokens over 684 seconds. It was
    well-formed, non-repeating prose the whole way, so both quality guards passed it — the
    relay's health probe then timed out against the busy upstream, marked the endpoint
    failed, and the next three turns came back 400. Only length sees that failure.

    With the sampler fixed (EXP-2026-08-007) a passage averages 674 characters and the
    longest of thirty was 1,923, so the stop sits roughly six times past the worst honest
    case: a backstop, not a leash.
    """
    from app.services.turn_engine import _DEGENERATE_AFTER_CHARS, _RUNAWAY_CHARS

    assert _RUNAWAY_CHARS >= 6 * 1923
    assert _RUNAWAY_CHARS > _DEGENERATE_AFTER_CHARS
