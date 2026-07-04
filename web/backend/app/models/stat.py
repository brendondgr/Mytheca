"""Stat schema seam.

``StatDefinition`` is the per-storyline baseline schema (range locked at
creation); ``CharacterStat`` is a single character's value for one stat, clamped
to the definition's ``[min, max]`` by the service/validator. Both are normalized
(queried/mutated independently) — unlike scenario branches, which are JSON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONColumn
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.storyline import Storyline


class StatDefinition(Base):
    __tablename__ = "stat_definitions"
    __table_args__ = (
        UniqueConstraint("storyline_id", "key", name="uq_stat_def_storyline_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("stat"))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    # Range + starting value are locked at creation and enforced by the validator.
    min: Mapped[int] = mapped_column(default=0)
    max: Mapped[int] = mapped_column(default=100)
    default: Mapped[int] = mapped_column(default=0)
    visibility: Mapped[str] = mapped_column(String, default="public")
    guidance: Mapped[str | None] = mapped_column(String, nullable=True)
    applies_to: Mapped[list[str]] = mapped_column(JSONColumn, default=lambda: ["character"])
    # Labeled value bands ("tickers") describing what ranges mean — e.g. health
    # 0-20 "nearly dead", 81-100 "very healthy". Ordered list of
    # {min,max,label,description?}; the optional per-band ``description`` (with a
    # ``{Character}`` placeholder) is surfaced to the acting character at play time.
    # Nullable so the dev DB self-heals via the additive-column reconcile.
    bands: Mapped[list[dict] | None] = mapped_column(JSONColumn, nullable=True, default=list)

    storyline: Mapped[Storyline] = relationship(back_populates="stat_definitions")


class CharacterStat(Base):
    __tablename__ = "character_stats"
    __table_args__ = (
        UniqueConstraint("character_id", "key", name="uq_char_stat_character_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("cs"))
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String)
    value: Mapped[int] = mapped_column(default=0)

    character: Mapped[Character] = relationship(back_populates="stats")
