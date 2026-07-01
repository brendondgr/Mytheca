"""Character — a person in a storyline (descriptive fields + a stat block)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONColumn
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.stat import CharacterStat
    from app.models.storyline import Storyline


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("c"))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="Character")
    color: Mapped[str] = mapped_column(String, default="#8E2B1C")
    mono: Mapped[str] = mapped_column(String, default="?")
    traits: Mapped[str] = mapped_column(String, default="")
    speech: Mapped[str] = mapped_column(String, default="")
    goal: Mapped[str] = mapped_column(String, default="")
    secret: Mapped[str] = mapped_column(String, default="")
    # Base-identity prose authored once (agentic Character Creator fills these).
    # Nullable so they self-heal on the persistent dev DB (see bootstrap reconcile);
    # these are §1 *node properties*, never graph structure.
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Relative URL of the generated WebP portrait (served under /media); monogram
    # is the fallback when unset.
    portrait: Mapped[str | None] = mapped_column(String, nullable=True)
    # The ComfyUI prompts that produced the portrait — persisted so the author can
    # tweak-and-re-render on re-edit instead of regenerating from scratch. Nullable
    # so they self-heal on the persistent dev DB (see bootstrap reconcile).
    portrait_positive: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    portrait_negative: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # Voice & tone profile — a small set of situation → sample-response pairs that
    # show *how* this character speaks, derived from their background/personality at
    # creation (before starting stats) and editable in the character menu. Injected
    # into the turn loop so both spoken lines and the hidden thinking step stay in
    # voice. Nullable so it self-heals on the persistent dev DB (bootstrap reconcile);
    # authored §1 node property, never graph structure. Each entry: {situation, sample}
    voice_samples: Mapped[list[dict] | None] = mapped_column(
        JSONColumn, nullable=True, default=list
    )
    position: Mapped[int] = mapped_column(default=0)

    storyline: Mapped[Storyline] = relationship(back_populates="characters")
    stats: Mapped[list[CharacterStat]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
