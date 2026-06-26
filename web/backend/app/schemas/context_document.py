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


# ---- Live triage stream (NDJSON) -------------------------------------------
#
# ``POST /storylines/triage/stream`` classifies one document per LLM call and
# emits these events (one JSON object per line) so the Triage panel can show each
# file being sorted live. The non-streaming ``/triage`` route still returns a
# single ``TriageResponse`` (one batched LLM call).


class TriageStatusEvent(CamelModel):
    """A document is being classified (drive the per-file working indicator)."""

    type: Literal["status"] = "status"
    name: str
    index: int
    total: int


class TriageItemEvent(CamelModel):
    """One document is classified — slot the result into its row."""

    type: Literal["item"] = "item"
    item: TriageItem


class TriageDoneEvent(CamelModel):
    """Terminal success event (every document has been classified)."""

    type: Literal["done"] = "done"


class TriageErrorEvent(CamelModel):
    """Terminal error event — emitted in-band once the 200 stream has opened."""

    type: Literal["error"] = "error"
    message: str


TriageEvent = TriageStatusEvent | TriageItemEvent | TriageDoneEvent | TriageErrorEvent
