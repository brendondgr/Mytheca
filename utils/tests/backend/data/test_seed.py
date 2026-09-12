"""The Embergate seed matches the frontend and is idempotent."""

from __future__ import annotations

from app.core.seed import SEED_STORYLINE_ID, seed_if_empty
from app.core.seed_docs import DOCUMENTS
from app.models import Character, Scenario, Setting, StatDefinition, Storyline


def test_seed_populates_embergate(db_session):
    assert seed_if_empty(db_session) is True

    storyline = db_session.get(Storyline, SEED_STORYLINE_ID)
    assert storyline.title == "Embergate"
    assert storyline.premise and "\n\n" in storyline.premise  # multi-paragraph world
    assert storyline.world_primer and "\n\n" in storyline.world_primer  # agent-facing primer
    assert db_session.query(Character).count() == 6
    assert db_session.query(Setting).count() == 7
    assert db_session.query(Scenario).count() == 3
    assert db_session.query(StatDefinition).count() == 4

    conspiracy = db_session.get(Scenario, "embergate")
    assert conspiracy.cast_ids == ["maerin", "aldous", "wren", "doran"]
    assert conspiracy.setting_id == "saltworn"
    assert conspiracy.branches[0]["tag"] == "check_request"  # tag preserved verbatim


def test_seed_is_idempotent(db_session):
    assert seed_if_empty(db_session) is True
    assert seed_if_empty(db_session) is False
    assert db_session.query(Character).count() == 6


def test_seed_ships_the_reference_corpus(db_session):
    """The retrieval gate has nothing to find on a fresh install without this."""
    from app.models import ContextDocument

    seed_if_empty(db_session)
    docs = db_session.query(ContextDocument).all()

    assert len(docs) == 8
    assert {d.name for d in docs} == {d["name"] for d in DOCUMENTS}
    assert all(d.include_rag for d in docs)  # the corpus is the point of them
    assert all(d.char_count == len(d.content) > 0 for d in docs)
    assert all(d.storyline_id == SEED_STORYLINE_ID for d in docs)


def test_corpus_documents_are_substantial_and_distinct():
    names = [d["name"] for d in DOCUMENTS]
    assert len(names) == len(set(names))
    # Short enough to sit in a prompt, long enough for a retrieval hit to be worth having.
    assert all(400 < len(d["content"]) < 6000 for d in DOCUMENTS)
