"""Incremental emission parsing (``EmissionAccumulator``).

The accumulator exists so a beat can be shown while it is still being written. It is
only safe to swap into the turn path if it changes *when* things appear and never *what*
appears — so most of this file pins it against :func:`parse_emission`, the batch parser
every existing turn test already trusts, under arbitrary chunking.
"""

from __future__ import annotations

import random

import pytest

from app.services.emission import EmissionAccumulator, Segment, parse_emission

ROSTER = {1: "char-a", 2: "char-b"}
FALLBACK = "char-fallback"


def _accumulate(raw: str, chunks: list[str] | None = None):
    """Feed ``raw`` (in ``chunks``, or one character at a time) and return the result."""
    acc = EmissionAccumulator(roster=ROSTER, fallback_speaker_id=FALLBACK)
    deltas = []
    for piece in chunks if chunks is not None else list(raw):
        deltas.extend(acc.push(piece))
    deltas.extend(acc.finish())
    return acc, deltas


def _batch(raw: str) -> list[Segment]:
    return parse_emission(raw, roster=ROSTER, fallback_speaker_id=FALLBACK)


def _random_chunks(raw: str, rng: random.Random) -> list[str]:
    chunks, i = [], 0
    while i < len(raw):
        size = rng.randint(1, 17)
        chunks.append(raw[i : i + size])
        i += size
    return chunks


# Fixtures follow the documented think→speak format the character agent actually emits.
EMISSIONS = [
    # The ordinary shape: speaker, thought, action, dialogue.
    '<speaker:1><thinking>He is hiding something.</thinking>'
    "<type:character_action>She sets down the cup.</type:character_action>"
    '<type:character_dialogue>"Where were you?"</type:character_dialogue>',
    # Dialogue only.
    '<speaker:2><type:character_dialogue>"Evening."</type:character_dialogue>',
    # No tags at all — the resilience path.
    "Just some prose with no tags whatsoever.",
    # A JSON body alongside prose.
    "<speaker:1><thinking>This hurts.</thinking>"
    '<type:character_dialogue>"I am fine."</type:character_dialogue>'
    '<type:state_update>{"key": "health", "delta": -2}</type:state_update>',
    # XML-style closing tags used as delimiters.
    "<speaker:1></type:character_dialogue>Hello there.</type:next>",
    # Untagged preamble before a real mark (batch discards it).
    "some preamble<speaker:1><type:character_dialogue>The real line.</type:character_dialogue>",
    # Whitespace everywhere.
    "<speaker:1>\n  <thinking>\n  Spaced out.\n  </thinking>\n"
    "  <type:character_dialogue>\n   Padded line.  \n</type:character_dialogue>  ",
    # Out-of-roster speaker number falls back.
    '<speaker:9><type:character_dialogue>"Who am I?"</type:character_dialogue>',
    # Several prose blocks in a row.
    "<speaker:2><type:character_action>He turns.</type:character_action>"
    "<type:character_action>He turns back.</type:character_action>"
    '<type:character_dialogue>"Well?"</type:character_dialogue>',
    # A presence change.
    "<speaker:1><type:character_dialogue>\"I am leaving.\"</type:character_dialogue>"
    '<type:presence_change>{"status": "left"}</type:presence_change>',
]


@pytest.mark.parametrize("raw", EMISSIONS)
def test_matches_the_batch_parser_one_character_at_a_time(raw):
    acc, _ = _accumulate(raw)
    assert acc.segments == _batch(raw)


@pytest.mark.parametrize("raw", EMISSIONS)
def test_matches_the_batch_parser_in_one_go(raw):
    acc, _ = _accumulate(raw, chunks=[raw])
    assert acc.segments == _batch(raw)


@pytest.mark.parametrize("raw", EMISSIONS)
def test_matches_the_batch_parser_under_random_chunking(raw):
    # Deterministic seed per fixture: a failure must be reproducible, and the point is
    # to cross chunk boundaries in many different places, not to be unpredictable.
    rng = random.Random(len(raw))
    for _ in range(40):
        acc, _ = _accumulate(raw, chunks=_random_chunks(raw, rng))
        assert acc.segments == _batch(raw)


@pytest.mark.parametrize("raw", EMISSIONS)
def test_joined_deltas_reproduce_each_segment_body(raw):
    """A consumer accumulating deltas by index must land on the exact segment text."""
    acc, deltas = _accumulate(raw)
    joined: dict[int, str] = {}
    for d in deltas:
        joined[d.index] = joined.get(d.index, "") + d.text
    for i, segment in enumerate(acc.segments):
        assert joined.get(i, "") == segment.text


# ---- streaming behaviour ---------------------------------------------------


def test_the_thought_completes_before_the_dialogue_starts():
    """The reason the whole feature exists: interiority lands early."""
    raw = (
        "<speaker:1><thinking>I should lie.</thinking>"
        '<type:character_dialogue>"Nothing happened."</type:character_dialogue>'
    )
    _, deltas = _accumulate(raw)

    thought_done = next(
        i for i, d in enumerate(deltas) if d.type == "internal_thought" and d.done
    )
    first_dialogue = next(i for i, d in enumerate(deltas) if d.type == "character_dialogue")
    assert thought_done < first_dialogue


def test_prose_arrives_in_pieces_rather_than_all_at_once():
    raw = '<speaker:1><type:character_dialogue>"One two three four five."</type:character_dialogue>'
    _, deltas = _accumulate(raw, chunks=[raw[:40], raw[40:]])

    text_deltas = [d for d in deltas if d.type == "character_dialogue" and d.text]
    assert len(text_deltas) > 1


def test_a_json_body_is_delivered_whole_and_never_in_fragments():
    """Half a JSON object is not usable — it must not be emitted mid-parse."""
    raw = '<speaker:1><type:state_update>{"key": "trust", "delta": 3}</type:state_update>'
    _, deltas = _accumulate(raw)

    updates = [d for d in deltas if d.type == "state_update"]
    assert len(updates) == 1
    assert updates[0].done is True
    assert updates[0].text == '{"key": "trust", "delta": 3}'


def test_a_tag_split_across_chunks_never_leaks_into_prose():
    raw = '<speaker:1><type:character_dialogue>"Hi."</type:character_dialogue>'
    # Slice straight through the middle of every tag.
    chunks = [raw[i : i + 3] for i in range(0, len(raw), 3)]
    acc, deltas = _accumulate(raw, chunks=chunks)

    emitted = "".join(d.text for d in deltas)
    assert "<" not in emitted and ">" not in emitted
    assert acc.segments == _batch(raw)


def test_deltas_carry_the_resolved_speaker():
    raw = '<speaker:2><type:character_dialogue>"Mine."</type:character_dialogue>'
    _, deltas = _accumulate(raw)
    assert {d.character_id for d in deltas} == {"char-b"}


def test_empty_emission_produces_nothing():
    acc, deltas = _accumulate("")
    assert acc.segments == []
    assert deltas == []


def test_whitespace_only_emission_produces_nothing():
    acc, deltas = _accumulate("   \n\t  ")
    assert acc.segments == []
    assert [d for d in deltas if d.text] == []


# ---- documented divergences ------------------------------------------------


def test_a_late_thought_streams_late_rather_than_being_reordered():
    """A stream cannot un-send what it has already sent.

    The batch parser lifts ``internal_thought`` to the front of the list wherever it
    appeared. Arrival order is the contract here, so a thought emitted after the
    dialogue stays after it. The character agent's format puts thinking first, so the
    two agree in practice — this pins the difference rather than hiding it.
    """
    raw = (
        '<type:character_dialogue>"Fine."</type:character_dialogue>'
        "<speaker:1><thinking>Actually not fine.</thinking>"
    )
    acc, _ = _accumulate(raw)

    assert [s.type for s in acc.segments] == ["character_dialogue", "internal_thought"]
    assert [s.type for s in _batch(raw)] == ["internal_thought", "character_dialogue"]
    # Same segments, same bodies — only the order differs.
    assert sorted((s.type, s.text) for s in acc.segments) == sorted(
        (s.type, s.text) for s in _batch(raw)
    )
