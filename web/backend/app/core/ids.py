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
