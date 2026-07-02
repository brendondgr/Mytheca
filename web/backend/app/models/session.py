"""PlaySession — a single play-through of a scenario.

Events (``app/models/event.py``) and diagnostic trace steps
(``app/models/turn_trace.py``) belong to a session. ``updated_at`` tracks recency so
the story player can resume a scenario's most recent play-through with its full
history; ``closed_at`` records an explicit close (the save-on-close signal).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
