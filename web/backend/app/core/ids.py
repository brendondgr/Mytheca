"""Server-side id generation.

String primary keys so hand-authored seed slugs (``embergate``, ``maerin``)
coexist with generated ids. ``POST`` accepts a client id when given; otherwise a
prefixed, collision-resistant id is generated here.
"""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Return a short prefixed id, e.g. ``c_1a2b3c4d5e``."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def new_hex_id(length: int) -> str:
    """Return a bare, prefix-free hex id of ``length`` chars, e.g. ``1a2b3c4d``.

    Used for the URL-facing ids: storyline (``length=8``) and scenario
    (``length=4``). The smaller scenario keyspace (16**4 = 65 536) means callers
    that generate these should collision-check against the store (see
    ``services.crud``).
    """
    return uuid.uuid4().hex[:length]
