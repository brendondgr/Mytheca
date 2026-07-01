"""Retrieval gate — the model-free skip-or-fetch heuristic."""

from __future__ import annotations

from app.services.retrieval_gate import gate, off_roster_terms

KNOWN = ["Embergate", "Mei", "Kira", "The Smoldering Hearth"]


def test_skips_pure_action_naming_only_the_roster():
    d = gate("I slide the coin pouch toward Mei and say nothing.", known_names=KNOWN)
    assert d.fetch is False


def test_fetches_on_an_off_roster_entity():
    d = gate("Isn't this the hearth where the Ashford warehouse fire started?", known_names=KNOWN)
    assert d.fetch is True
    assert "Ashford" in d.reason


def test_fetches_on_a_world_history_question():
    d = gate("what happened here years ago?", known_names=KNOWN)
    assert d.fetch is True
    assert "history" in d.reason


def test_titles_in_the_stoplist_do_not_trigger():
    assert gate("I nod to the Captain by the door.", known_names=KNOWN).fetch is False


def test_roster_name_midsentence_skips():
    assert gate("I turn to Kira and wait.", known_names=KNOWN).fetch is False


def test_empty_input_skips():
    assert gate("   ", known_names=KNOWN).fetch is False


def test_off_roster_terms_dedupes_and_filters_known():
    terms = off_roster_terms(
        "Maerin Voss met the Ironworks Guild near Embergate.", ["Maerin Voss", "Embergate"]
    )
    assert "Ironworks Guild" in terms
    assert "Maerin Voss" not in terms and "Embergate" not in terms
