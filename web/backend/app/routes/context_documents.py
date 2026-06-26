"""Context-document routes — the persisted triaged RAG corpus.

Storyline-scoped list / create / bulk-create, then flat item update / delete.
The corpus is written by the New Storyline page (Triage → commit); retrieval over
it is a later plan, so nothing reads ``content`` at runtime yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.context_document import (
    ContextDocumentBulkCreate,
    ContextDocumentCreate,
    ContextDocumentRead,
    ContextDocumentUpdate,
)
from app.services import crud

router = APIRouter(tags=["context-documents"])


@router.get(
    "/storylines/{storyline_id}/context-docs",
    response_model=list[ContextDocumentRead],
)
def list_context_documents(storyline_id: str, db: Session = Depends(get_db)):
    return crud.list_context_documents(db, storyline_id)


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
