"""Entity → lore entry adapters (brief §0.1)."""

from __future__ import annotations

from app.models import Character, ContextDocument, Scenario, Setting, Storyline
from app.rag.entries import (
    entry_from_character,
    entry_from_context_document,
    entry_from_scenario,
    entry_from_setting,
    entry_from_storyline,
)
from app.rag.schema import EntryType


def test_storyline_entry_is_lore_scoped_to_itself():
    sl = Storyline(
        id="w1", title="Embergate", genre="Maritime",
        tagline="salt and sorrow", premise="A drowned city.", world_primer="Primer text.",
    )
    e = entry_from_storyline(sl)
    assert e.fm.type is EntryType.lore
    assert e.fm.name == "Embergate"
    assert e.fm.summary == "salt and sorrow"
    assert "Maritime" in e.fm.tags
    assert "Primer text." in e.body and "A drowned city." in e.body
    assert e.storyline_id == "w1" and e.entity_type == "storyline" and e.entity_id == "w1"


def test_character_entry_maps_traits_and_prose():
    ch = Character(
        id="c1", storyline_id="w1", name="Maerin", role="Warden",
        traits="brave, loyal · haunted", goal="protect the harbor",
        appearance="tall, weathered", background="orphaned at sea",
        personality="stoic", speech="clipped", secret="is a spy",
    )
    e = entry_from_character(ch)
    assert e.fm.type is EntryType.character
    assert e.fm.tags == ["brave", "loyal", "haunted"]
    assert "Warden" in e.fm.summary and "protect the harbor" in e.fm.summary
    assert "orphaned at sea" in e.body
    assert "Secret: is a spy" in e.body
    assert e.entity_type == "character" and e.entity_id == "c1"


def test_setting_entry_is_a_location():
    st = Setting(
        id="s1", storyline_id="w1", name="The Wharf", type="Harbor",
        desc="A creaking pier.", atmosphere="brine and tar",
        features="rotting jetties", current_state="fog at dawn",
    )
    e = entry_from_setting(st)
    assert e.fm.type is EntryType.location
    assert e.fm.location == "The Wharf"
    assert "Harbor" in e.fm.tags
    assert "brine and tar" in e.body and "fog at dawn" in e.body
    assert e.entity_type == "setting"


def test_scenario_entry_is_an_event_with_genre_tone_tags():
    sc = Scenario(
        id="sc1", storyline_id="w1", title="Low Tide", genre="Mystery",
        tone="Tense", goal="find the body", opening="The fog rolls in.",
    )
    e = entry_from_scenario(sc)
    assert e.fm.type is EntryType.event
    assert e.fm.name == "Low Tide"
    assert "Mystery" in e.fm.tags and "Tense" in e.fm.tags
    assert "find the body" in e.fm.summary
    assert "The fog rolls in." in e.body


def test_context_document_entry_inherits_category_type_and_rag_flag():
    doc = ContextDocument(
        id="cd1", storyline_id="w1", name="maerin.md",
        content="The salt below remembers her name.", category="character",
        include_rag=True,
    )
    e = entry_from_context_document(doc)
    assert e.fm.type is EntryType.character  # category → type
    assert e.fm.name == "maerin.md"
    assert e.body == "The salt below remembers her name."
    assert e.include_rag is True
    assert e.entity_type == "context_document" and e.entity_id == "cd1"


def test_context_document_other_category_is_lore():
    doc = ContextDocument(id="cd2", storyline_id="w1", name="world.md",
                          content="History of the realm.", category="other", include_rag=False)
    e = entry_from_context_document(doc)
    assert e.fm.type is EntryType.lore
    assert e.include_rag is False
