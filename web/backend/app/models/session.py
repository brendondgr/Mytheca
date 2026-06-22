"""PlaySession — a single play-through of a scenario (chat scaffold).

Data-structure scaffold only: no turn engine or streaming yet. Events
(``app/models/event.py``) belong to a session.
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
