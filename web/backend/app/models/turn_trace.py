"""TurnTrace — one persisted diagnostic trace step for a play turn.

The turn engine streams opt-in :class:`~app.events.stream.TurnTraceFrame`s (the
Inspector's step-by-step "what the loop did and why" — intent, RAG/lore look-up,
speaker choice, hidden thinking, stat clamps, the graph ``commit``/``relationships``
writes, reflection). Those frames are transport-only on the wire, but Velora also
**persists a copy here** so a reopened scene can be reviewed and exported in full
after the fact — including the graph and RAG activity that would otherwise be lost.

Rows are ordered by ``(turn, n)``: ``turn`` is the turn's opening ``user_turn`` seq
(``seq0`` in :func:`app.services.turn_engine.run_turn`) and ``n`` is the per-turn
ordinal the tracer already stamps. Kept out of the ``events`` table so the
``(session_id, seq)`` monotonic invariant on story events is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONColumn
from app.core.ids import new_id


class TurnTrace(Base):
    __tablename__ = "turn_traces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("tt"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    turn: Mapped[int] = mapped_column(Integer, default=0)
    n: Mapped[int] = mapped_column(Integer, default=0)
    step: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[str] = mapped_column(String, default="")
    data: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
