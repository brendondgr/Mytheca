"""Character — a person in a storyline (descriptive fields + a stat block)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
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
    position: Mapped[int] = mapped_column(default=0)

    storyline: Mapped[Storyline] = relationship(back_populates="characters")
    stats: Mapped[list[CharacterStat]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
