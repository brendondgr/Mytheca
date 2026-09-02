"""Cues and disclosure: reaching a memory nobody in the room was part of, without leaking it.

The two halves are inseparable. Cues are what make a memory reachable when its people are
dead or absent; disclosure is what stops that reach from handing the room knowledge it was
never given. Shipping the first without the second would be a downgrade on the feature that
does not have either.
"""

from __future__ import annotations

import pytest

from app.models import CharacterMemory
from app.services import memory_cues, memory_recall
from app.services.memory_cues import PRIVATE, QUOTABLE, SHARED


# ---- cues --------------------------------------------------------------------


def test_the_scene_naming_a_thing_reaches_the_memory_about_it():
    """The ogre case, which participant matching cannot solve at all.

    A character who watched an ogre kill a friend has that friend in no further scene, so
    "who is in the room" can never surface the memory that most defines him.
    """
    assert memory_cues.scan(
        ["An ogre steps out of the treeline."], {"ogres", "the-north-road"}
    ) == {"ogres"}


def test_a_tag_inside_a_longer_word_does_not_fire():
    assert memory_cues.scan(["The maratime charter was signed."], {"mara"}) == set()
    assert memory_cues.scan(["He was undrowned."], {"drowning"}) == set()


def test_a_multi_word_tag_matches_the_words_as_written():
    assert memory_cues.scan(
        ["They went back down into the flooded tunnel."], {"flooded-tunnel"}
    ) == {"flooded-tunnel"}


def test_a_single_trailing_s_is_tolerated_in_both_directions():
    """`normalize_subject` folds articles but not plurals; this absorbs that near-miss."""
    assert memory_cues.scan(["An ogre."], {"ogres"}) == {"ogres"}
    assert memory_cues.scan(["Two ogres."], {"ogre"}) == {"ogre"}


def test_the_allowance_is_one_character_not_a_stemmer():
    assert memory_cues.scan(["He drew his knives."], {"knife"}) == set()


def test_punctuation_and_case_do_not_block_a_match():
    assert memory_cues.scan(['"OGRES!" he shouted.'], {"ogres"}) == {"ogres"}


def test_scanning_nothing_finds_nothing():
    assert memory_cues.scan([], {"ogres"}) == set()
    assert memory_cues.scan(["An ogre."], set()) == set()


# ---- disclosure --------------------------------------------------------------


def test_everyone_here_was_there_makes_it_quotable():
    assert memory_cues.disclosure(["ch_dell", "ch_mara"], others_present={"ch_mara"}) == QUOTABLE


def test_a_mixed_room_makes_it_shared_not_quotable():
    assert memory_cues.disclosure(
        ["ch_dell", "ch_mara"], others_present={"ch_mara", "ch_kell"}
    ) == SHARED


def test_nobody_here_was_there_makes_it_private():
    """The leak this exists to stop: narrating it hands the room what it was never told."""
    assert memory_cues.disclosure(["ch_dell", "ch_sera"], others_present={"ch_mara"}) == PRIVATE


def test_an_empty_room_leaves_nothing_to_leak_to():
    assert memory_cues.disclosure([], others_present=set()) == QUOTABLE


def test_outsiders_names_exactly_who_was_not_there():
    assert memory_cues.outsiders(
        ["ch_dell", "ch_mara"], others_present={"ch_mara", "ch_kell"}
    ) == {"ch_kell"}


# ---- how it reaches the prompt ----------------------------------------------


def _mem(**kw) -> CharacterMemory:
    base = dict(
        id="cm_1", storyline_id="w1", character_id="ch_dell", session_id="ps1",
        scenario_id="sc1", turn_seq=4, gloss="an ogre killed Sera in front of me",
        quote="Run, Dell.", salience=0.9, participants=["ch_dell", "ch_sera"],
        subjects=["ogres"], reinforcements=0,
    )
    base.update(kw)
    return CharacterMemory(**base)


class _Member:
    def __init__(self, cid, name):
        self.id, self.name = cid, name


class _Ctx:
    def __init__(self, recalled, cast):
        self.recalled = recalled
        self.cast = cast


def _note(item):
    from app.services import beat_runner

    cast = [_Member("ch_dell", "Dell"), _Member("ch_mara", "Mara"), _Member("ch_sera", "Sera")]
    return beat_runner.memory_note(_Ctx({"ch_dell": [item]}, cast), "ch_dell")


def test_a_private_memory_is_never_offered_as_a_quote():
    """Reaching a memory and being allowed to say it are different questions."""
    note = _note(
        memory_recall.Recalled(
            memory=_mem(), score=1.0, disclosure=PRIVATE, outsiders=["ch_mara"]
        )
    )
    assert "Run, Dell." not in note
    assert "you may quote this back" not in note
    assert "an ogre killed Sera in front of me" in note  # it still shapes the beat


def test_a_private_memory_names_who_must_not_learn_it():
    """"Mara does not know this" is actionable; "do not narrate private memories" is not."""
    note = _note(
        memory_recall.Recalled(
            memory=_mem(), score=1.0, disclosure=PRIVATE, outsiders=["ch_mara"]
        )
    )
    assert "Mara does not know this" in note
    assert "Do not tell it" in note and "Let it show" in note


def test_a_shared_memory_may_be_alluded_to_but_not_quoted():
    note = _note(
        memory_recall.Recalled(
            memory=_mem(), score=1.0, disclosure=SHARED, outsiders=["ch_mara"]
        )
    )
    assert "you may quote this back" not in note
    assert "Mara was not there" in note


def test_a_quotable_memory_keeps_its_verbatim_line():
    note = _note(
        memory_recall.Recalled(memory=_mem(), score=1.0, disclosure=QUOTABLE, outsiders=[])
    )
    assert '"Run, Dell."' in note and "you may quote this back" in note
    assert "does not know this" not in note


def test_ranking_attaches_the_disclosure_class_and_the_outsiders():
    picked = memory_recall.rank(
        [_mem()], session_id="ps1", now_seq=5, present_ids={"ch_mara"}, cues={"ogres"}
    )
    assert picked[0].disclosure == PRIVATE
    assert picked[0].outsiders == ["ch_mara"]
    assert picked[0].cue_hits == ["ogres"]


# ---- promotion ---------------------------------------------------------------


class _Mem:
    def __init__(self, subjects, scenario_id="sc1"):
        self.subjects = subjects
        self.scenario_id = scenario_id


def test_a_tag_that_keeps_coming_up_earns_a_node():
    """`ogres` becomes a node in a world precisely because ogres kept mattering."""
    corpus = [_Mem(["ogres"]), _Mem(["ogres", "rain"]), _Mem(["ogres"])]
    assert memory_cues.promotable(corpus) == {"ogres": 3}


def test_a_tag_mentioned_once_does_not(): 
    """Without the threshold every noun anyone mentions becomes a permanent node."""
    assert memory_cues.promotable([_Mem(["a-lantern"]), _Mem(["rain"])]) == {}


def test_spanning_two_scenarios_is_enough_on_its_own():
    """Recurring across scenes is a stronger signal than recurring within one."""
    corpus = [_Mem(["the-ledger"], "sc1"), _Mem(["the-ledger"], "sc2")]
    assert memory_cues.promotable(corpus) == {"the-ledger": 2}


def test_one_memory_repeating_a_tag_counts_once():
    assert memory_cues.promotable([_Mem(["ogres", "ogres"])]) == {}
