"""Setting — a place within a storyline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONColumn
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.storyline import Storyline


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("s"))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String, default="Social Hub")
    # Base description — the short overview/mood line shown on the card.
    desc: Mapped[str] = mapped_column(String, default="")
    # Setting Node metadata (Documents/Plans/4.story-graph-structure-prep.md §4.1),
    # authored once by the agentic Setting Creator. These are §1 *node properties*,
    # never graph structure (no edges, no Event/Faction nodes, no Neo4j). Nullable
    # so they self-heal on the persistent dev DB via the additive-column reconcile.
    #  - atmosphere: sensory character (sights, sounds, smells, light, texture)
    #  - features: notable physical features / fixtures / points of interest
    #  - current_state: the initial mutable here-and-now (time, weather, lighting,
    #    what's open/barred) — fast-changing scenario state seeded at authoring
    atmosphere: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Relative URL of an optional establishing image (served under /media); the
    # striped "setting plate" is the fallback when unset. Parity with Character.portrait.
    image: Mapped[str | None] = mapped_column(String, nullable=True)
    # Event timeline (§4.1) — an append-only log of durable things that happen here,
    # accruing across scenarios. **Empty at authoring** and populated only by the
    # async worker once play exists (read-live/write-async, §6); shipped now as the
    # seam so a place can later *remember*. Each entry:
    #   {summary, origin:{scenario,turn}, participants, kind, visibility}
    timeline: Mapped[list[dict] | None] = mapped_column(JSONColumn, nullable=True, default=list)
    position: Mapped[int] = mapped_column(default=0)

    storyline: Mapped[Storyline] = relationship(back_populates="settings")
