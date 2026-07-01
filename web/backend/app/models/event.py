"""Event — one persisted story event.

Mirrors the NDJSON envelope (``docs/api-contract.md``): a typed row with a JSON
``data`` payload. ``seq`` is monotonic **per session** (the turn engine assigns
``max(seq)+1`` via ``services.events_store.next_seq``); the
``(session_id, seq)`` unique constraint makes that monotonicity a hard invariant
and catches any concurrent-write race.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONColumn
from app.core.ids import new_id


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_event_session_seq"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("ev"))
    type: Mapped[str] = mapped_column(String)
    seq: Mapped[int] = mapped_column(default=0)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    visibility: Mapped[str] = mapped_column(String, default="public")
    data: Mapped[dict] = mapped_column(JSONColumn, default=dict)
