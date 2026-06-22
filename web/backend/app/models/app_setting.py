"""AppSetting — a portable key/value store for global application settings.

There is no auth/users table yet, so settings are a single **global** document
per namespace (``"llm"``, ``"library"``). Each row holds an opaque JSON blob; the
schema lives in ``app/schemas/settings.py``, not in the column type, so namespaces
stay flexible. When auth lands, add an owner column and scope per user.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONColumn


class AppSetting(Base):
    __tablename__ = "app_settings"

    # Namespace key, e.g. "llm" or "library".
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONColumn, default=dict)
