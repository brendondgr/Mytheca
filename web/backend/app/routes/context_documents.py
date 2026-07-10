"""Context-document routes — the persisted triaged RAG corpus.

Storyline-scoped list / create / bulk-create, then flat item update / delete.
The corpus is written by the New Storyline page (Triage → commit); retrieval over
it is a later plan, so nothing reads ``content`` at runtime yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.context_document import (
    ContextDocumentBulkCreate,
    ContextDocumentCreate,
    ContextDocumentLinkCreate,
    ContextDocumentRead,
    ContextDocumentUpdate,
)
from app.services import crud

router = APIRouter(tags=["context-documents"])


@router.get(
    "/storylines/{storyline_id}/context-docs",
    response_model=list[ContextDocumentRead],
)
def list_context_documents(
    storyline_id: str,
    entity_type: str | None = Query(default=None, alias="entityType"),
    entity_id: str | None = Query(default=None, alias="entityId"),
    linked_entity_type: str | None = Query(default=None, alias="linkedEntityType"),
    linked_entity_id: str | None = Query(default=None, alias="linkedEntityId"),
    db: Session = Depends(get_db),
):
    """List a world's context docs. Pass ``entityType``+``entityId`` to scope to one
    editor's OWNED files (they reappear on edit); pass ``linkedEntityType``+
    ``linkedEntityId`` for the docs an entity is a context REFERENCE of (provenance)."""
    return crud.list_context_documents(
        db,
        storyline_id,
        entity_type=entity_type,
        entity_id=entity_id,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
    )


@router.post(
    "/storylines/{storyline_id}/context-docs",
    response_model=ContextDocumentRead,
    status_code=201,
)
def create_context_document(
    storyline_id: str, data: ContextDocumentCreate, db: Session = Depends(get_db)
):
    return crud.create_context_document(db, storyline_id, data)


@router.post(
    "/storylines/{storyline_id}/context-docs/bulk",
    response_model=list[ContextDocumentRead],
    status_code=201,
)
def bulk_create_context_documents(
    storyline_id: str, data: ContextDocumentBulkCreate, db: Session = Depends(get_db)
):
    return crud.bulk_create_context_documents(db, storyline_id, data.docs)


@router.patch("/context-docs/{doc_id}", response_model=ContextDocumentRead)
def update_context_document(
    doc_id: str, data: ContextDocumentUpdate, db: Session = Depends(get_db)
):
    return crud.update_context_document(db, doc_id, data)


@router.delete("/context-docs/{doc_id}", status_code=204)
def delete_context_document(doc_id: str, db: Session = Depends(get_db)):
    crud.delete_context_document(db, doc_id)


@router.post("/context-docs/{doc_id}/links", response_model=ContextDocumentRead)
def add_context_document_link(
    doc_id: str, data: ContextDocumentLinkCreate, db: Session = Depends(get_db)
):
    """Link a document to a character/setting/scenario as a context reference (idempotent)."""
    return crud.add_document_link(db, doc_id, data.entity_type, data.entity_id)


@router.delete("/context-docs/{doc_id}/links", response_model=ContextDocumentRead)
def remove_context_document_link(
    doc_id: str,
    entity_type: str = Query(alias="entityType"),
    entity_id: str = Query(alias="entityId"),
    db: Session = Depends(get_db),
):
    """Remove a document→entity provenance link (leaves the document itself). Idempotent."""
    return crud.remove_document_link(db, doc_id, entity_type, entity_id)
