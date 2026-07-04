"""Scenario — a situation within a storyline.

``cast_ids`` and ``branches`` are stored as JSON (wholesale-edited value data,
no independent identity). ``setting_id`` is a *soft* reference validated in the
service layer — like ``cast_ids``, it may point at a since-deleted setting, and
the frontend falls back gracefully (``resolveScenario``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
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
    # Per-scene play controls (Scene Dialogue Updates). ``max_turns`` is the hard
    # ceiling on character replies per player message (the turn loop may still end
    # earlier); ``suggestions_count`` is how many follow-up suggestions to offer at
    # the end of a turn (0 disables; max 4, rendered as a 2×2 grid). ``context_beats``
    # is the depth of the recent-transcript window the character conditions on (5–100).
    max_turns: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    suggestions_count: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    context_beats: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    # Per-scenario writing-prompt overrides ({registry key -> prompt text}) — override the
    # storyline's prompts for THIS scene only. Empty {} inherits storyline/global/default.
    # Nullable (older rows read as {}); resolved by ``prompt_registry.resolve_prompts``.
    prompt_overrides: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True, default=dict)
    # Scene art generated for this scenario (opt-in, requires ComfyUI).
    image: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_positive: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_negative: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    storyline: Mapped[Storyline] = relationship(back_populates="scenarios")
