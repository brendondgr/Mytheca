"""Scenario — a situation within a storyline.

``cast_ids`` and ``branches`` are stored as JSON (wholesale-edited value data,
no independent identity). ``setting_id`` is a *soft* reference validated in the
service layer — like ``cast_ids``, it may point at a since-deleted setting, and
the frontend falls back gracefully (``resolveScenario``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, text
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
    # ``beat_length`` is how much a CHARACTER says in one beat — short 1-2 paragraphs,
    # medium 2-4 (the default, and closest to what shipped before this existed), long 5-6,
    # each paragraph at most 3-4 sentences not counting quoted dialogue. It shapes the
    # character prompt's recency TAIL and the per-tier prose allowance; it does NOT touch
    # narration, which has its own sentence spec. A string rather than a number because it
    # is an enum the UI names, not a quantity anything does arithmetic on.
    # ``text("'medium'")``, not a bare "medium": a bare string is emitted verbatim into the
    # DDL, and `DEFAULT medium` is a COLUMN REFERENCE to Postgres, which refuses it. The
    # integer columns above get away with a bare string because `14` is already a valid
    # literal. SQLite accepts either, so the whole test suite passes while the backend
    # fails to boot on the real database — the additive reconciler runs this DDL at
    # preflight, so it is the first thing that breaks.
    beat_length: Mapped[str] = mapped_column(
        String, default="medium", server_default=text("'medium'")
    )
    # Per-scenario writing-prompt overrides ({registry key -> prompt text}) — override the
    # storyline's prompts for THIS scene only. Empty {} inherits storyline/global/default.
    # Nullable (older rows read as {}); resolved by ``prompt_registry.resolve_prompts``.
    prompt_overrides: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True, default=dict)
    # How the transcript window is chosen. ``"auto"`` (the default; ``NULL`` reads as auto)
    # fits it to the model's real context budget each turn; ``"fixed"`` honours
    # ``context_beats`` below, which is otherwise ignored. Nullable, so the additive
    # reconciler adds it with a plain ADD COLUMN and no Alembic migration is required.
    context_policy: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # The named preset the play controls above were last set from
    # (``content/scene_presets``), or NULL for *Custom*. It records the player's INTENT, not
    # a source of truth: the controls stay authoritative, and moving one leaves this set so
    # the UI can say "modified" and offer a reset. Nullable, so the additive reconciler adds
    # it with a plain ADD COLUMN and no Alembic migration is required — deliberately with no
    # ``server_default``, because "no preset" is a real and common state.
    scene_preset: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # Whether the ReAct planner decides each beat (``"planner"``, and NULL reads as that) or
    # the model-free scripted order does (``"off"`` — ``services/beat_order``). Nullable so
    # every existing scene reads as today's behaviour.
    planner_mode: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # The scene's OWN one-tap direction verbs, appended to the built-in bar's groups.
    # ``[{"label", "group", "text"}]``. Nullable (older rows read as none), so
    # ``core/bootstrap._reconcile_additive_columns`` adds it with a plain ADD COLUMN and no
    # Alembic migration is required.
    direction_verbs: Mapped[list | None] = mapped_column(JSONColumn, nullable=True, default=None)
    # Scene art generated for this scenario (opt-in, requires ComfyUI).
    image: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_positive: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    scene_art_negative: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    storyline: Mapped[Storyline] = relationship(back_populates="scenarios")
