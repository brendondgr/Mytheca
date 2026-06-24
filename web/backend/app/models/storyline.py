"""Storyline — the top-level world container.

Owns its characters, settings, scenarios, and the baseline stat schema. Deleting
a storyline cascades to all of them (ORM ``delete-orphan`` so it works on both
Postgres and SQLite).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.scenario import Scenario
    from app.models.setting import Setting
    from app.models.stat import StatDefinition


class Storyline(Base):
    __tablename__ = "storylines"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("sl"))
    title: Mapped[str] = mapped_column(String, default="Untitled Storyline")
    genre: Mapped[str] = mapped_column(String, default="Uncharted")
    tagline: Mapped[str | None] = mapped_column(String, nullable=True)
    # Long-form, multi-paragraph world description authored in the create modal.
    # ``premise`` is human-facing Library copy; ``world_primer`` (below) is the
    # agent-facing runtime context injected into conversations — same world, a
    # different audience.
    premise: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Agent-facing world context generated at creation (seed + premise + an
    # optional overview of dropped docs), then editable. Injected verbatim into
    # every conversation so the model can open cold without day-one retrieval.
    world_primer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Customizable seal shown left of the storyline's name: a simple shape glyph
    # plus a hex color. Defaults to the historical gold diamond.
    symbol: Mapped[str] = mapped_column(String, default="◆")
    symbol_color: Mapped[str] = mapped_column(String, default="#C8862A")
    position: Mapped[int] = mapped_column(default=0)

    characters: Mapped[list[Character]] = relationship(
        back_populates="storyline",
        cascade="all, delete-orphan",
        order_by="Character.position",
    )
    settings: Mapped[list[Setting]] = relationship(
        back_populates="storyline",
        cascade="all, delete-orphan",
        order_by="Setting.position",
    )
    scenarios: Mapped[list[Scenario]] = relationship(
        back_populates="storyline",
        cascade="all, delete-orphan",
        order_by="Scenario.position",
    )
    stat_definitions: Mapped[list[StatDefinition]] = relationship(
        back_populates="storyline",
        cascade="all, delete-orphan",
    )
