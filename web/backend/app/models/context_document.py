"""ContextDocument — a triaged reference document attached to a storyline.

The durable corpus produced by the **Triage** step of the New Storyline page:
each dropped ``.txt``/``.md`` file is classified into a ``category``
(``character`` | ``setting`` | ``other``) and tagged for inclusion in **Draft**
(world-setting documents that ground generation) and/or **RAG** (the retrieval
corpus). This model is the persisted corpus for that retrieval. Documents are embedded
into Qdrant on save (``app/rag/indexer.py``) and retrieved by the authoring
agents (``app/rag/retriever.py``). A document may be **storyline-level** (the
Triage default — ``entity_type``/``entity_id`` null) or **entity-scoped** to a
single character/setting/scenario, in which case it reappears in that editor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.storyline import Storyline


class ContextDocument(Base):
    __tablename__ = "context_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("cd"))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    # Original file name (e.g. ``maerin.md``) — the corpus key the UI shows.
    name: Mapped[str] = mapped_column(String)
    # Full document text read in-browser at triage time and persisted verbatim.
    content: Mapped[str] = mapped_column(Text, default="")
    # Triage classification: a doc about ONE character → "character"; ONE setting →
    # "setting"; multiple/mixed characters or settings, or a general world doc →
    # "other". Stored as a plain string; the schema constrains the value set.
    category: Mapped[str] = mapped_column(String, default="other")
    # Inclusion tiers chosen at triage. ``include_draft`` ⇒ world-setting docs that
    # ground Velora's drafting; ``include_rag`` ⇒ the retrieval corpus (default on);
    # ``include_extract`` ⇒ OPT-IN: mine this doc for named characters/settings during
    # **Build the whole world** (default OFF — a new storyline never auto-extracts).
    # Non-null with a server default so existing rows backfill and the additive-column
    # reconciler self-heals it.
    include_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    include_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    include_extract: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false(), default=False
    )
    # Where the document came from (``upload`` today; future: ``event``, ``paste``).
    source: Mapped[str] = mapped_column(String, default="upload")
    # Optional entity scope. When set, the document belongs to a specific
    # character/setting/scenario — it reappears in *that* editor and is removed when
    # the entity is deleted. When null it is a storyline-level corpus doc (the Triage
    # default). ``entity_type`` ∈ {character, setting, scenario}. Nullable so they
    # self-heal on the persistent dev DB via the additive-column reconcile.
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Cached length of ``content`` so list views can show size / estimate budget
    # without shipping the full text.
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    storyline: Mapped[Storyline] = relationship(back_populates="context_documents")
    # Provenance links to the entities this document was used as context for (which
    # character/setting it helped build, or ones the author linked manually). Distinct
    # from ``entity_type``/``entity_id`` above (that is single-valued OWNERSHIP that
    # cascade-deletes with the entity); a link is a many-to-many REFERENCE that leaves
    # the doc a storyline-level corpus member. Deleting the doc drops its links.
    links: Mapped[list[ContextDocumentLink]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ContextDocumentLink(Base):
    """A doc→entity provenance reference (many-to-many).

    Records that a context document was used as context for a specific
    character/setting (auto-captured when **Build the whole world** mines a doc into
    that entity, plus any the author links by hand from the editor). Unlike the
    document's own ``entity_type``/``entity_id`` scope, a link never changes the
    document's storyline-level membership and one doc may link to several entities.
    """

    __tablename__ = "context_document_links"
    __table_args__ = (
        UniqueConstraint("doc_id", "entity_type", "entity_id", name="uq_ctxdoc_link"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("cdl"))
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("context_documents.id", ondelete="CASCADE"), index=True
    )
    # The linked entity — ``entity_type`` ∈ {character, setting, scenario}.
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    document: Mapped[ContextDocument] = relationship(back_populates="links")
