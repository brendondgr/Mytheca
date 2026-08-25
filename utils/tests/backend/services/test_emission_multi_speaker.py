"""One continuous emission, several speakers — the parsing half of `sceneFlow: "continuous"`.

The turn loop has always made one model call per speaker, and the parser was built to match:
`EmissionAccumulator._prose_seen` made a second passage **structurally unrepresentable**,
because a model repeating its emission had produced five byte-identical persisted beats that
read as five beats by the same character.

Continuous prose needs a hand-off to be representable without letting that defect back in.
The distinction that does it: a `<speaker:N>` naming somebody NEW hands the floor over; one
naming the CURRENT speaker changes nothing. A repeat is the same speaker again, so it still
collapses; a hand-off is somebody else, so it opens a segment.

Both parsers are exercised on every case. They have to agree — a test in
`test_emission_incremental.py` already says so in general, and the batch parser is what a
re-roll and an export read, so a disagreement is a beat that changes when you reload.
"""

from __future__ import annotations

import random

import pytest

from app.services.emission import EmissionAccumulator, parse_emission

ROSTER = {1: "c_lily", 2: "c_zoe", 3: "c_aldous"}
FALLBACK = "c_lily"


def _batch(raw: str):
    return parse_emission(raw, roster=ROSTER, fallback_speaker_id=FALLBACK)


def _accumulate(raw: str, chunks: list[str] | None = None):
    acc = EmissionAccumulator(roster=ROSTER, fallback_speaker_id=FALLBACK)
    for chunk in chunks or [raw]:
        acc.push(chunk)
    acc.finish()
    return acc


def _shred(raw: str, seed: int) -> list[str]:
    """Split into random chunks — a real stream arrives in arbitrary pieces."""
    rng = random.Random(seed)
    out, i = [], 0
    while i < len(raw):
        step = rng.randint(1, 7)
        out.append(raw[i : i + step])
        i += step
    return out


SCRIPT = (
    "Lily is on the table before anyone can stop her.\n\n"
    "<speaker:2>\n"
    "I catch her by the hem and pull.\n\n"
    "<speaker:3>\n"
    "The ink is bleeding across the ledger and nobody is watching it but me."
)


def test_a_hand_off_opens_a_new_segment_for_the_new_speaker():
    segments = _batch(SCRIPT)
    assert [s.character_id for s in segments] == ["c_lily", "c_zoe", "c_aldous"]
    assert all(s.type == "character_prose" for s in segments)
    assert segments[0].text.startswith("Lily is on the table")
    assert segments[1].text.startswith("I catch her by the hem")
    assert segments[2].text.startswith("The ink is bleeding")


def test_both_parsers_agree_on_a_multi_speaker_script():
    acc = _accumulate(SCRIPT)
    assert [(s.type, s.text, s.character_id) for s in acc.segments] == [
        (s.type, s.text, s.character_id) for s in _batch(SCRIPT)
    ]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_both_parsers_agree_under_random_chunking(seed):
    """A speaker tag can arrive split across two chunks; the parser must not miss it."""
    acc = _accumulate(SCRIPT, _shred(SCRIPT, seed))
    assert [(s.type, s.text, s.character_id) for s in acc.segments] == [
        (s.type, s.text, s.character_id) for s in _batch(SCRIPT)
    ]


def test_restating_the_current_speaker_is_not_a_hand_off():
    """Models re-state the current speaker constantly.

    Treating that as a hand-off would fragment one passage into a dozen byte-adjacent beats
    — which is the same shape of defect `_prose_seen` was written to prevent, arriving from
    the other direction.
    """
    raw = "<speaker:1>I set the cup down.<speaker:1> I do not look up.<speaker:1> Not yet."
    segments = _batch(raw)
    assert len(segments) == 1
    assert segments[0].character_id == "c_lily"
    assert "Not yet." in segments[0].text
    acc = _accumulate(raw)
    assert [(s.type, s.text, s.character_id) for s in acc.segments] == [
        (s.type, s.text, s.character_id) for s in segments
    ]


def test_a_repeated_passage_by_one_speaker_still_collapses_to_one_beat():
    """The defect `_prose_seen` exists for, and which must survive the hand-off change.

    A live beat produced the same ~2,400 characters five times over. Split into five events
    it read as five beats by the same character, each looking correct. Kept whole it is one
    ugly passage, which `repeats_itself` can then act on.
    """
    passage = "I will not go back to that house. " * 3
    raw = f"<speaker:1>{passage}<type:state_update>\n{{}}\n{passage}"
    segments = _batch(raw)
    prose = [s for s in segments if s.type == "character_prose"]
    assert len(prose) == 1, "a repeat is the same speaker again, so it must not open a beat"
    acc = _accumulate(raw)
    assert [(s.type, s.character_id) for s in acc.segments] == [
        (s.type, s.character_id) for s in segments
    ]


def test_an_out_of_roster_number_is_not_a_hand_off():
    """A model naming a speaker who is not on the roster must not produce an orphan beat.

    It resolves to whoever is already speaking, so the passage simply continues — the same
    fallback the single-speaker path has always used, and the reason a weak model degrades to
    one attributed beat rather than to an unattributed one.
    """
    raw = "<speaker:1>I speak.<speaker:9> And I keep speaking."
    segments = _batch(raw)
    assert len(segments) == 1
    assert segments[0].character_id == "c_lily"
    assert "keep speaking" in segments[0].text


def test_a_json_block_belongs_to_the_speaker_who_was_talking():
    """A stat change is a consequence of a beat, so it must not land on the next speaker."""
    raw = (
        "<speaker:2>I take the ledger.\n"
        '<type:state_update>\n{"key": "trust", "delta": -1, "reason": "she took it"}\n'
        "<speaker:3>I watch her take it."
    )
    segments = _batch(raw)
    by_kind = {(s.type, s.character_id) for s in segments}
    assert ("state_update", "c_zoe") in by_kind
    assert ("character_prose", "c_aldous") in by_kind
    acc = _accumulate(raw)
    assert [(s.type, s.character_id) for s in acc.segments] == [
        (s.type, s.character_id) for s in segments
    ]


def test_a_thought_still_only_counts_before_any_prose():
    """The anti-loop-back rule is emission-wide, and a hand-off must not reopen it.

    `<thinking>` is only a deliberation when it arrives before the writing starts. A block
    after ANY prose is a model looping back to the top of its own emission, whoever is
    nominally speaking — so a hand-off must not let a second thought through the door that
    guard exists to hold shut.
    """
    raw = "<speaker:1>I speak first.<speaker:2><thinking>Second thoughts.</thinking>I answer."
    segments = _batch(raw)
    assert not [s for s in segments if s.type == "internal_thought"]
    acc = _accumulate(raw)
    assert [(s.type, s.character_id) for s in acc.segments] == [
        (s.type, s.character_id) for s in segments
    ]


def test_a_script_with_no_speaker_tags_is_unchanged():
    """The single-speaker path — every existing turn — must be byte-identical."""
    raw = "I look at the door. I do not move.\n\n\"You first,\" I say."
    segments = _batch(raw)
    assert len(segments) == 1
    assert segments[0].character_id == FALLBACK
    assert segments[0].text == raw
