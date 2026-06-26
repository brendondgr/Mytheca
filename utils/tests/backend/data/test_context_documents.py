"""ContextDocument model — roundtrip + cascade with the owning storyline."""

from __future__ import annotations

from app.models import ContextDocument, Storyline


def test_context_document_roundtrip(db_session):
    sl = Storyline(id="w1", title="World", genre="Test")
    db_session.add(sl)
    db_session.commit()

    doc = ContextDocument(
        storyline_id="w1",
        name="lore.md",
        content="The salt below remembers.",
        category="other",
        include_draft=True,
        include_rag=True,
        char_count=len("The salt below remembers."),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id.startswith("cd_")
    assert doc.category == "other"
    assert doc.include_draft is True
    assert sl.context_documents[0].name == "lore.md"


def test_context_documents_cascade_delete(db_session):
    sl = Storyline(id="w2", title="World", genre="Test")
    sl.context_documents.append(ContextDocument(name="a.md", category="character"))
    sl.context_documents.append(ContextDocument(name="b.md", category="setting"))
    db_session.add(sl)
    db_session.commit()
    assert db_session.query(ContextDocument).count() == 2

    db_session.delete(sl)
    db_session.commit()
    # Deleting the world removes its corpus (delete-orphan cascade).
    assert db_session.query(ContextDocument).count() == 0
