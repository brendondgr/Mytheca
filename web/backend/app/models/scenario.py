"""Scenario — a situation within a storyline.

``cast_ids`` and ``branches`` are stored as JSON (wholesale-edited value data,
no independent identity). ``setting_id`` is a *soft* reference validated in the
service layer — like ``cast_ids``, it may point at a since-deleted setting, and
the frontend falls back gracefully (``resolveScenario``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONColumn
from app.core.ids import new_hex_id

if TYPE_CHECKING:
    from app.models.storyline import Storyline


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_hex_id(4))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    genre: Mapped[str] = mapped_column(String, default="Custom")
    tone: Mapped[str] = mapped_column(String, default="Unset")
    goal: Mapped[str] = mapped_column(String, default="")
    setting_id: Mapped[str] = mapped_column(String, default="", index=True)
    opening: Mapped[str] = mapped_column(String, default="")
    cast_ids: Mapped[list[str]] = mapped_column(JSONColumn, default=list)
    branches: Mapped[list[dict]] = mapped_column(JSONColumn, default=list)
    position: Mapped[int] = mapped_column(default=0)
    # Scene art generated for this scenario (opt-in, requires ComfyUI).
    image: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_positive: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_negative: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    storyline: Mapped[Storyline] = relationship(back_populates="scenarios")
