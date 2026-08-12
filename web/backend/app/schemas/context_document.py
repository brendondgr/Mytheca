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


# Entity scope for a context document. ``None`` = storyline-level (Triage default);
# otherwise the doc belongs to a specific character/setting/scenario editor.
EntityScope = Literal["character", "setting", "scenario"]


class ContextDocumentBase(CamelModel):
    name: str
    content: str = ""
    category: DocCategory = "other"
    include_draft: bool = False
    include_rag: bool = True
    # Opt-in: mine this doc for named characters/settings during the world build.
    # Default OFF so a new storyline never auto-extracts (the author checks it per file).
    include_extract: bool = False
    source: str = "upload"
    entity_type: EntityScope | None = None
    entity_id: str | None = None


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
    include_extract: bool | None = None


class ContextDocumentLinkRead(CamelModel):
    """A doc→entity provenance link (which character/setting a doc is context for)."""

    id: str
    entity_type: EntityScope
    entity_id: str


class ContextDocumentLinkCreate(CamelModel):
    """Attach a document to an entity as a context reference (idempotent)."""

    entity_type: EntityScope
    entity_id: str


class ContextDocumentRead(CamelModel):
    id: str
    storyline_id: str
    name: str
    content: str
    category: DocCategory
    include_draft: bool
    include_rag: bool
    include_extract: bool
    source: str
    char_count: int
    entity_type: EntityScope | None = None
    entity_id: str | None = None
    # Provenance links: the entities this doc was used as context for (build lineage
    # + manual links). Read straight off the ORM ``links`` relationship.
    links: list[ContextDocumentLinkRead] = []


class ContextDocumentIndexEntry(CamelModel):
    """One document, name-only — the shape the story player's ``@`` menu lists.

    Deliberately omits ``content``: the picker needs a label and a size, and a world with
    thirty large files would otherwise ship every body just to open a dropdown. The full
    text is never fetched by the client at all — the player sends ids and the turn engine
    loads the text server-side (see ``assembler._tagged_notes``).
    """

    id: str
    name: str
    category: DocCategory
    char_count: int
    entity_type: EntityScope | None = None
    entity_id: str | None = None


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
    # Suggested opt-in for build-time extraction — conservative (only a clear,
    # single, explicitly-named character/setting profile), default OFF.
    include_extract: bool = False
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
