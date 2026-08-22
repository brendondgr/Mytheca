"""Stat schema seam.

``StatDefinition`` is the per-storyline baseline schema (range locked at creation).

There are **two** places a value lives, and the distinction matters:

* :class:`CharacterStat` — the character's **authored baseline**, edited from the Library
  and written by world population. One row per character per stat.
* :class:`SessionCharacterStat` — the value **inside one play-through**. Play reads and
  writes here, so two play-throughs of a scenario no longer share a health value and a
  rewind can roll one back without touching the other.

Resolution when play reads a stat: the session's row → else, if the definition sets
``carry_over``, the character's baseline → else the definition's ``default``. Owner decision
D-1 (2026-08-21); before it, every value was character-global and a branch silently
inherited whatever the last play-through had done.

All values are clamped to the definition's ``[min, max]`` by the service/validator.
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
    #: Whether a play-through inherits the character's authored baseline for this stat, or
    #: starts from ``default``. ``None`` reads as **False** — each play-through starts clean,
    #: which is what makes a branch and a rewind predictable. Turn it on for a stat that
    #: should follow a character between scenes (a permanent injury, a standing reputation).
    #: Nullable so the additive-column reconciler self-heals a drifted dev DB.
    carry_over: Mapped[bool | None] = mapped_column(nullable=True, default=False)

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
    # The value the AUTHOR wrote, kept recoverable.
    #
    # ``value`` is not safe to treat as authored: ``session_stats.carry_forward`` overwrites
    # it at session close for any stat marked ``carry_over``, so a character who has been
    # played once no longer remembers what they were written with. Play itself never touches
    # this table (D-1 — it writes ``SessionCharacterStat``), so this column exists for
    # exactly one hazard: the carry-forward write.
    #
    # NULL means "never carried over, so ``value`` is still the authored one". Set on an
    # authoring write, and captured once by the first carry-forward that would destroy it.
    baseline: Mapped[int | None] = mapped_column(nullable=True, default=None)

    character: Mapped[Character] = relationship(back_populates="stats")


class SessionCharacterStat(Base):
    """One character's value for one stat **inside one play-through**.

    Play writes here rather than to :class:`CharacterStat`, which is why a branch diverges
    instead of sharing, and why a rewind can replay the surviving ``state_update`` events
    from the authored baseline without needing per-event provenance.

    Absent row = the value has not moved in this play-through yet; the reader falls back
    through ``carry_over`` to the baseline or the definition default.
    """

    __tablename__ = "session_character_stats"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "character_id", "key", name="uq_session_stat_session_char_key"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("scs"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String)
    value: Mapped[int] = mapped_column(default=0)
