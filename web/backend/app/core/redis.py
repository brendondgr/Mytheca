"""Redis client factory and a health helper.

The live/cache layer (active scenario state, stream pub/sub) is built in later
phases. For now this provides a lazily-created client and a ``ping`` used by the
preflight checks (``app/core/bootstrap.py``).
"""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    """Return the cached Redis client bound to ``REDIS_URL``."""
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def ping() -> bool:
    """Return True if Redis answers PING; never raises (used by preflight)."""
    try:
        return bool(get_redis().ping())
    except Exception:
        return False
