"""Setting — a place within a storyline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import new_id

if TYPE_CHECKING:
    from app.models.storyline import Storyline


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("s"))
    storyline_id: Mapped[str] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String, default="Social Hub")
    desc: Mapped[str] = mapped_column(String, default="")
    position: Mapped[int] = mapped_column(default=0)

    storyline: Mapped[Storyline] = relationship(back_populates="settings")
