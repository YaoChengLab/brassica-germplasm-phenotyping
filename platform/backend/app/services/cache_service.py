"""
Redis cache-aside service for v2 API.
"""

import json
import logging
from typing import Any, Callable, Optional

import redis

from ..config.settings import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Simple Redis cache-aside helper."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        if redis_client is not None:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis not available, caching disabled: {e}")
                self.redis = None

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def get_or_set(self, key: str, fetch_fn: Callable, ttl: int = 300) -> Any:
        """
        Return cached value for *key*, or call *fetch_fn*, cache the result,
        and return it.  If Redis is unavailable, always call *fetch_fn*.
        """
        if self.redis is None:
            return fetch_fn()

        try:
            cached = self.redis.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read error for key={key}: {e}")

        result = fetch_fn()

        try:
            self.redis.setex(key, ttl, json.dumps(result, default=str))
        except Exception as e:
            logger.warning(f"Cache write error for key={key}: {e}")

        return result

    def invalidate(self, pattern: str) -> int:
        """Delete all keys matching *pattern* (glob-style)."""
        if self.redis is None:
            return 0
        deleted = 0
        try:
            for key in self.redis.scan_iter(pattern):
                self.redis.delete(key)
                deleted += 1
        except Exception as e:
            logger.warning(f"Cache invalidation error for pattern={pattern}: {e}")
        return deleted

    def delete(self, key: str) -> bool:
        """Delete a single cache key."""
        if self.redis is None:
            return False
        try:
            return bool(self.redis.delete(key))
        except Exception as e:
            logger.warning(f"Cache delete error for key={key}: {e}")
            return False
