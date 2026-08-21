"""A character beat is ONE passage, however badly the model behaves.

Live session ``ps_0f0d1a6900``, turn 10: trace steps 29–36 are a single ``speaker`` step
("Aldous responds"), one ``thinking`` step, and then **five** consecutive ``prose`` steps
whose bodies are byte-identical. One LLM call; five persisted ``character_prose`` events,
which read to the player as five beats by the same character.

The cause was structural rather than statistical: a ``<thinking>`` tag closed the open
segment in either direction, so the next word opened a fresh passage. A model that loops
back to the top of its own emission was therefore split faithfully, one event per loop.
"""

from __future__ import annotations

from app.services.emission import (
    EmissionAccumulator,
    parse_emission,
    repeats_itself,
)

ROSTER = {1: "char-a"}
FALLBACK = "char-a"

PASSAGE = (
    "The trailing end of her unfinished sentence still sits wet in front of me like ink "
    "dropped onto an open page before anyone has decided what word it will become."
)
# What the model actually did: think, write, think again, write the same thing again.
LOOPED = (
    "<thinking>Let me sit with what just happened.</thinking>"
    + PASSAGE
    + "<thinking>Let me sit with what just happened.</thinking>"
    + PASSAGE
    + "<thinking>Let me sit with what just happened.</thinking>"
    + PASSAGE
)


def _accumulate(raw: str, chunks: list[str] | None = None) -> EmissionAccumulator:
    acc = EmissionAccumulator(roster=ROSTER, fallback_speaker_id=FALLBACK)
    for piece in chunks if chunks is not None else list(raw):
        acc.push(piece)
    acc.finish()
    return acc


def _batch(raw: str):
    return parse_emission(raw, roster=ROSTER, fallback_speaker_id=FALLBACK)


def test_a_looping_emission_is_one_passage_not_five():
    acc = _accumulate(LOOPED)
    prose = [s for s in acc.segments if s.type == "character_prose"]
    assert len(prose) == 1


def test_the_repeated_deliberation_never_reaches_the_prose():
    """The loop repeats the scratchpad too; only the first one is a thought."""
    acc = _accumulate(LOOPED)
    assert [s.type for s in acc.segments] == ["internal_thought", "character_prose"]
    body = next(s for s in acc.segments if s.type == "character_prose").text
    assert "Let me sit with what just happened" not in body


def test_both_parsers_agree_on_a_looping_emission():
    acc = _accumulate(LOOPED)
    assert [(s.type, s.text) for s in acc.segments] == [(s.type, s.text) for s in _batch(LOOPED)]


def test_agreement_survives_chunking_straight_through_the_tags():
    chunks = [LOOPED[i : i + 5] for i in range(0, len(LOOPED), 5)]
    acc = _accumulate(LOOPED, chunks=chunks)
    assert [(s.type, s.text) for s in acc.segments] == [(s.type, s.text) for s in _batch(LOOPED)]


def test_text_after_a_json_block_does_not_start_a_second_beat():
    """A model still talking after its state block is not taking another turn."""
    raw = (
        PASSAGE
        + '<type:state_update>{"key": "trust", "delta": 1}</type:state_update>'
        + "And then I say it all over again."
    )
    acc = _accumulate(raw)
    assert [s.type for s in acc.segments] == ["character_prose", "state_update"]


def test_the_loop_is_visible_as_repetition_once_the_passage_is_whole():
    """Keeping the passage whole is only an improvement if something then sees the loop."""
    assert repeats_itself(PASSAGE * 3) is True
    assert repeats_itself(PASSAGE) is False


def test_repetition_is_not_confused_with_a_refrain():
    """People repeat a phrase for effect; two hundred characters is not a phrase."""
    refrain = (
        "I will not go back. The rain keeps its count against the glass and I let it. "
        "I will not go back. He knows it, and he is waiting for me to say so out loud. "
        "I will not go back."
    )
    assert repeats_itself(refrain) is False


def test_a_short_passage_is_never_called_a_repeat():
    assert repeats_itself("") is False
    assert repeats_itself("Again. Again. Again.") is False


def test_an_invented_wrapper_tag_is_scrubbed_not_rendered():
    """Observed live twice: a whole passage delivered inside a tag nobody asked for.

    A verification run produced ``<response>\\nThe mist clings to my cheeks…\\n</response>``
    and the tag was persisted into the rendered prose; an earlier beat opened on a bare
    ``<passage>``. As a complete tag these words are never prose.
    """
    raw = '<response>\nThe mist clings to my cheeks.\n\n"Deeper," I whisper.\n</response>'
    acc = _accumulate(raw)
    assert [(s.type, s.text) for s in acc.segments] == [
        ("character_prose", 'The mist clings to my cheeks.\n\n"Deeper," I whisper.')
    ]
    assert [(s.type, s.text) for s in _batch(raw)] == [(s.type, s.text) for s in acc.segments]


def test_the_wrapper_never_reaches_the_stream_either():
    """Scrubbed at parse time, so it does not flicker on screen before the beat closes."""
    acc = EmissionAccumulator(roster=ROSTER, fallback_speaker_id=FALLBACK)
    deltas = []
    for piece in list("<passage>I hold still at the edge of him."):
        deltas.extend(acc.push(piece))
    deltas.extend(acc.finish())
    assert "<" not in "".join(d.text for d in deltas)


def test_a_word_that_merely_contains_a_wrapper_name_is_untouched():
    """"The passage behind the kitchen" is prose; only a complete tag is scrubbed."""
    raw = "I take the passage behind the kitchen and wait for his answer."
    assert _batch(raw)[0].text == raw
