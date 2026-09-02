"""CharacterMemory — one character's episodic memory of one moment.

The durable half of what a character carries between scenarios. Before this table the
only thing that survived a scene boundary was a relationship edge in Neo4j: a verb and a
weight, with the *reason* written to a ``:Consequence`` node nothing ever read and the
per-character retrospective written to a Redis key with a one-day TTL. A cast that
carries feelings forward with no idea where they came from invents replacement reasons,
routinely contradicting scenes the player actually played.

**Postgres is canonical here**, unlike the rest of the Story Graph. Neo4j gets a
mirrored ``remembers`` edge for traversal, but a memory is not best-effort: it must
survive without Docker, be deleted transactionally by a rewind, and be testable on the
offline SQLite path the whole suite runs on.

Two fields carry most of the weight:

``quote``
    A line copied **verbatim** from the transcript, with ``quote_speaker_id``. This is
    what lets a character throw a line back three scenarios later instead of reporting
    that something once happened. ``services.memory_store`` refuses to persist a quote
    that is not a substring of a real ``events`` row, so a character cannot quote a line
    nobody said.

``subjects``
    What the moment was *about* — character ids, the setting id, and free tags like
    ``ogres`` or ``drowning``. Participants alone cannot reach a memory whose people are
    dead or absent; subjects are how a character who watched an ogre kill a friend can
    still recall it, in a later scenario, with nobody from that night in the room.

Memories are **subjective and may be wrong**. Two characters can hold contradicting
memories of the same source event; that is the design, not a defect, and the objective
record stays in the ``events`` rows underneath.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONColumn
from app.core.ids import new_id


class CharacterMemory(Base):
    __tablename__ = "character_memories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("cm"))

    #: Recall never crosses a storyline. A Character row belongs to exactly one, and
    #: there is no identity above it, so this is the outermost scope that exists.
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    #: Whose memory this is — not who it is about.
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    #: Where it was formed. Drives both rewind (delete by session + seq) and lineage
    #: (a forked play-through must not recall the timeline it walked away from).
    session_id: Mapped[str] = mapped_column(
        ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    turn_seq: Mapped[int] = mapped_column(Integer, default=0)

    #: The story event to jump back to when the player asks where a line came from.
    #: Nullable and *not* a cascade-delete dependency: a memory outlives an edited beat.
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)

    #: What the moment meant to this character, in their own words. One short line.
    gloss: Mapped[str] = mapped_column(String, default="")
    #: A line copied verbatim from the transcript, or NULL when nothing was worth keeping.
    quote: Mapped[str | None] = mapped_column(String, nullable=True)
    quote_speaker_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: How it sits with them — ``wound`` / ``warmth`` / ``fear`` / ``debt`` / ``shame`` /
    #: ``awe``. Free text, not an enum: the vocabulary belongs to the writing agent and
    #: constraining it here would mean a migration every time the prompt gains a word.
    valence: Mapped[str] = mapped_column(String, default="")

    #: 0..1 — how much it mattered. The write filter rejects below a floor; recall
    #: multiplies by it.
    salience: Mapped[float] = mapped_column(Float, default=0.0)

    #: Character ids present at the source event. Drives the "who is in the room" cue
    #: and, with the present cast, the quotable/shared/private disclosure class.
    participants: Mapped[list] = mapped_column(JSONColumn, default=list)
    #: Normalised subject tags — see the module docstring.
    subjects: Mapped[list] = mapped_column(JSONColumn, default=list)

    #: How many times the moment has been re-lived. A grudge that keeps getting picked at
    #: stays hot; a slight nobody mentions again fades to the floor.
    reinforcements: Mapped[int] = mapped_column(Integer, default=0)
    last_recalled_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_recalled_session_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        # Recall's one query per turn: every planned speaker's memories in this world.
        Index("ix_character_memories_owner", "storyline_id", "character_id"),
        # Rewind's delete, and the lineage cut at a fork point.
        Index("ix_character_memories_origin", "session_id", "turn_seq"),
    )
