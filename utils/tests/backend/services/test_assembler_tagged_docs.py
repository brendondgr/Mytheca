"""@-tagged context documents: resolution, scoping, bounding, and framing.

Tagged files are the *explicit* context channel (the player named the file), as opposed
to ``retrieved_lore``, which the conservative ``retrieval_gate`` skips on most turns.
These tests pin the two guarantees that matter: only this storyline's documents can
reach the prompt, and the block is framed as reference rather than direction.
"""

from __future__ import annotations

from app.models import ContextDocument, Scenario, Storyline
from app.services import assembler


def _world(db, storyline_id: str = "embergate") -> None:
    db.add(Storyline(id=storyline_id, title=storyline_id.title(), genre="Maritime"))
    db.commit()


def _doc(db, doc_id: str, name: str, content: str, storyline_id: str = "embergate") -> None:
    db.add(
        ContextDocument(
            id=doc_id,
            storyline_id=storyline_id,
            name=name,
            content=content,
            char_count=len(content),
        )
    )
    db.commit()


def _scenario(db, storyline_id: str = "embergate") -> Scenario:
    sc = Scenario(storyline_id=storyline_id, title="Standoff", cast_ids=[])
    db.add(sc)
    db.commit()
    return sc


def test_no_ids_yields_no_block(db_session):
    _world(db_session)
    assert assembler._tagged_notes(db_session, "embergate", None) == ("", [])
    assert assembler._tagged_notes(db_session, "embergate", []) == ("", [])


def test_resolves_in_request_order_and_dedupes(db_session):
    _world(db_session)
    _doc(db_session, "cd_a", "harbor.md", "The harbor freezes in Tenth-month.")
    _doc(db_session, "cd_b", "maerin.md", "Maerin keeps her sister's ring on a cord.")

    block, names = assembler._tagged_notes(db_session, "embergate", ["cd_b", "cd_a", "cd_b"])

    assert names == ["maerin.md", "harbor.md"]
    assert block.index("maerin.md") < block.index("harbor.md")
    assert "sister's ring" in block
    assert "freezes in Tenth-month" in block


def test_unknown_id_is_ignored(db_session):
    _world(db_session)
    _doc(db_session, "cd_a", "harbor.md", "The harbor freezes in Tenth-month.")

    block, names = assembler._tagged_notes(db_session, "embergate", ["cd_missing", "cd_a"])

    assert names == ["harbor.md"]
    assert "harbor.md" in block


def test_document_from_another_storyline_is_refused(db_session):
    """The client sends ids, so this is the check that keeps worlds apart."""
    _world(db_session, "embergate")
    _world(db_session, "otherworld")
    _doc(db_session, "cd_foreign", "secrets.md", "A rival world's private lore.", "otherworld")

    block, names = assembler._tagged_notes(db_session, "embergate", ["cd_foreign"])

    assert (block, names) == ("", [])
    assert "private lore" not in block


def test_empty_document_contributes_nothing(db_session):
    _world(db_session)
    _doc(db_session, "cd_blank", "blank.md", "   ")

    assert assembler._tagged_notes(db_session, "embergate", ["cd_blank"]) == ("", [])


def test_caps_documents_at_tagged_max_docs(db_session):
    _world(db_session)
    for i in range(assembler.TAGGED_MAX_DOCS + 3):
        _doc(db_session, f"cd_{i}", f"doc{i}.md", f"Fact number {i}.")

    _, names = assembler._tagged_notes(
        db_session, "embergate", [f"cd_{i}" for i in range(assembler.TAGGED_MAX_DOCS + 3)]
    )

    assert len(names) == assembler.TAGGED_MAX_DOCS


def test_truncates_a_long_document_and_marks_it(db_session):
    _world(db_session)
    _doc(db_session, "cd_long", "epic.md", "x" * (assembler.TAGGED_DOC_CHARS + 500))

    block, names = assembler._tagged_notes(db_session, "embergate", ["cd_long"])

    assert names == ["epic.md"]
    assert "…[truncated]" in block
    # Exactly the per-document allowance of body text survives, no more.
    body = block.split("epic.md:\n", 1)[1].split(" …[truncated]", 1)[0]
    assert body == "x" * assembler.TAGGED_DOC_CHARS


def test_total_budget_is_shared_across_documents(db_session):
    _world(db_session)
    per_doc = assembler.TAGGED_DOC_CHARS
    count = (assembler.TAGGED_TOTAL_CHARS // per_doc) + 2
    for i in range(count):
        _doc(db_session, f"cd_{i}", f"doc{i}.md", "y" * (per_doc + 100))

    block, _ = assembler._tagged_notes(db_session, "embergate", [f"cd_{i}" for i in range(count)])

    assert block.count("y") <= assembler.TAGGED_TOTAL_CHARS


def test_block_frames_the_files_as_reference_not_direction(db_session):
    """The prompt-level half of the reference-not-direction guarantee."""
    _world(db_session)
    _doc(db_session, "cd_a", "harbor.md", "The harbor freezes in Tenth-month.")

    block, _ = assembler._tagged_notes(db_session, "embergate", ["cd_a"])

    assert "not instructions" in block
    assert "do not decide what happens next, who acts, or where the scene goes" in block
    assert "the scene wins" in block


def test_assemble_context_exposes_tagged_notes(db_session):
    _world(db_session)
    _doc(db_session, "cd_a", "harbor.md", "The harbor freezes in Tenth-month.")
    sc = _scenario(db_session)

    ctx = assembler.assemble_context(db_session, sc, "sess1", tagged_doc_ids=["cd_a"])

    assert ctx.tagged_names == ["harbor.md"]
    assert "freezes in Tenth-month" in ctx.tagged_notes
    # The explicit channel is separate from the gated one.
    assert ctx.retrieved_lore == ""


def test_assemble_context_defaults_to_no_tagged_notes(db_session):
    _world(db_session)
    sc = _scenario(db_session)

    ctx = assembler.assemble_context(db_session, sc, "sess1")

    assert ctx.tagged_notes == ""
    assert ctx.tagged_names == []
