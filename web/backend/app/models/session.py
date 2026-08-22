"""PlaySession — a single play-through of a scenario.

Events (``app/models/event.py``) and diagnostic trace steps
(``app/models/turn_trace.py``) belong to a session. ``updated_at`` tracks recency so
the story player can resume a scenario's most recent play-through with its full
history; ``closed_at`` records an explicit close (the save-on-close signal).

A scenario may hold **many** play-throughs, listed and switched between in the story
player's play-through tray. ``name`` is the player's own label for one (``None`` falls
back to its first player line). ``parent_session_id`` + ``fork_seq`` record lineage: a
branch copies the parent's history up to and including ``fork_seq`` and then diverges,
and a rewind uses the same mechanism to keep a pre-cut snapshot. All three are
**nullable**, so ``core/bootstrap._reconcile_additive_columns`` self-heals a drifted dev
DB with a plain ``ADD COLUMN`` and no Alembic migration is required — the same posture
``updated_at`` documents below.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import new_id


class PlaySession(Base):
    __tablename__ = "play_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("ps"))
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # Bumped on every turn (and on an explicit close) so the story player can resume the
    # most recent play-through of a scenario. ``closed_at`` records an explicit close.
    # ``server_default=now()`` lets the additive reconciler self-heal this non-null column
    # on a drifted dev DB (see core/bootstrap._reconcile_additive_columns).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The player's own label for this play-through; ``None`` renders as its first player line.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Lineage. Set together: the session this one forked from, and the parent ``Event.seq``
    # the copy ran through (inclusive). ``SET NULL`` so deleting a parent orphans the fork
    # rather than cascading the child play-through away with it.
    parent_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("play_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fork_seq: Mapped[int | None] = mapped_column(nullable=True)
