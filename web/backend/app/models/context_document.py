"""ContextDocument — a triaged reference document attached to a storyline.

The durable corpus produced by the **Triage** step of the New Storyline page:
each dropped ``.txt``/``.md`` file is classified into a ``category``
(``character`` | ``setting`` | ``other``) and tagged for inclusion in **Draft**
(world-setting documents that ground generation) and/or **RAG** (the retrieval
corpus). This model is the *persistence seam* for that corpus — the documents are
really stored and survive reload. Actual retrieval (chunking, embeddings, hybrid
search) is still deferred; nothing reads ``content`` at runtime yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
    # ground Velora's drafting; ``include_rag`` ⇒ the retrieval corpus (default on).
    include_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    include_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    # Where the document came from (``upload`` today; future: ``event``, ``paste``).
    source: Mapped[str] = mapped_column(String, default="upload")
    # Cached length of ``content`` so list views can show size / estimate budget
    # without shipping the full text.
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    storyline: Mapped[Storyline] = relationship(back_populates="context_documents")
