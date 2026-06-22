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
    premise: Mapped[str | None] = mapped_column(Text, nullable=True)
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
