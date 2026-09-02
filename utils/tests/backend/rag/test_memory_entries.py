"""Memories in the hybrid corpus — the first thing in it that *happened*.

Everything the corpus held before this was authored before play: storylines, characters,
settings, scenarios, documents. Indexing memories is what lets one be found by **meaning**
when the exact tag scan misses.
"""

from __future__ import annotations

from app.models import CharacterMemory
from app.rag import entries


def _memory(**kw) -> CharacterMemory:
    base = dict(
        id="cm_1", storyline_id="w1", character_id="ch_dell", session_id="ps1",
        scenario_id="sc1", turn_seq=4,
        gloss="an ogre killed Sera in front of me",
        quote="Run, Dell.", salience=0.9, subjects=["ogres", "the-north-road"],
        participants=["ch_dell"], reinforcements=0,
    )
    base.update(kw)
    return CharacterMemory(**base)


def test_a_memory_becomes_an_entry_owned_by_the_character_who_holds_it():
    """Dell's version and Mara's version of one turn are two entries, not one.

    They are two memories, and recall only ever wants the asking character's own.
    """
    entry = entries.entry_from_memory(_memory(), owner_name="Dell")
    assert entry.entity_type == "memory" and entry.entity_id == "cm_1"
    assert entry.storyline_id == "w1"
    assert "Dell remembers" in entry.body
    assert "an ogre killed Sera" in entry.body


def test_the_verbatim_line_is_in_the_indexed_body():
    entry = entries.entry_from_memory(_memory(), owner_name="Dell")
    assert "Run, Dell." in entry.body


def test_a_quoteless_memory_indexes_cleanly():
    entry = entries.entry_from_memory(_memory(quote=None), owner_name="Dell")
    assert "Someone said" not in entry.body
    assert entry.body.strip().endswith("in front of me")


def test_subjects_ride_as_tags_so_the_sparse_half_can_match_them():
    entry = entries.entry_from_memory(_memory(), owner_name="Dell")
    assert entry.fm.tags == ["ogres", "the-north-road"]


def test_the_entry_id_is_the_memory_id():
    """Recall intersects search hits with its candidate ids by this exact equality."""
    assert entries.entry_from_memory(_memory(), owner_name="Dell").fm.id == "cm_1"
