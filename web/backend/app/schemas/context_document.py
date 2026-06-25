"""Context-document schemas — the persisted triaged RAG corpus + Triage shapes.

``ContextDocumentRead`` mirrors the frontend ``ContextDocument`` type. ``category``
is constrained to the three triage buckets. The Triage request/response shapes
(used by ``agents.triage_agent`` + ``POST /storylines/triage``) live here too since
they describe the same documents pre-persistence.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel

# The three triage buckets. A doc about ONE character/setting lands in that
# bucket; multiple/mixed or a general world doc lands in "other".
DocCategory = Literal["character", "setting", "other"]


class ContextDocumentBase(CamelModel):
    name: str
    content: str = ""
    category: DocCategory = "other"
    include_draft: bool = False
    include_rag: bool = True
    source: str = "upload"


class ContextDocumentCreate(ContextDocumentBase):
    id: str | None = None


class ContextDocumentBulkCreate(CamelModel):
    """Persist a whole triaged corpus in one call (the New Storyline commit)."""

    docs: list[ContextDocumentCreate] = []


class ContextDocumentUpdate(CamelModel):
    name: str | None = None
    content: str | None = None
    category: DocCategory | None = None
    include_draft: bool | None = None
    include_rag: bool | None = None


class ContextDocumentRead(CamelModel):
    id: str
    storyline_id: str
    name: str
    content: str
    category: DocCategory
    include_draft: bool
    include_rag: bool
    source: str
    char_count: int


# ---- Triage (the agentic classification step) -------------------------------
# Classify dropped reference text into the three buckets + Draft/RAG inclusion.
# The documents are not persisted by this call; the page persists them on commit
# via ContextDocumentBulkCreate. ``text`` is the in-browser-read file content.


class TriageDoc(CamelModel):
    name: str
    text: str = ""


class TriageRequest(CamelModel):
    docs: list[TriageDoc] = []
    # Optional: ground the classification in a specific world (its primer/genre).
    storyline_id: str | None = None


class TriageItem(CamelModel):
    name: str
    category: DocCategory = "other"
    include_draft: bool = False
    include_rag: bool = True
    rationale: str = ""


class TriageResponse(CamelModel):
    items: list[TriageItem] = []
