"""Redis-backed alert deduplication client.

Falls back to an in-process dict when Redis is unavailable (fail-open:
dedup is disabled, not the whole service).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RedisDeduplicator:
    def __init__(self) -> None:
        self._available = False
        self._mock_store: dict = {}
        try:
            import redis
            self._client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379"),
                socket_connect_timeout=2,
            )
            self._client.ping()
            self._available = True
            logger.info("RedisDeduplicator: connected to Redis")
        except Exception as exc:
            logger.warning("RedisDeduplicator: Redis unavailable (%s) — dedup disabled", exc)

    def check(self, fingerprint: str) -> Optional[str]:
        """Return the existing incident_id if this fingerprint is a known dup, else None."""
        if not self._available:
            return self._mock_store.get(fingerprint)
        try:
            val = self._client.get(f"dedup:{fingerprint}")
            return val.decode() if val else None
        except Exception as exc:
            logger.warning("RedisDeduplicator.check failed: %s", exc)
            return None

    def set(self, fingerprint: str, incident_id: str, ttl: int = 3600) -> None:
        """Register a fingerprint → incident_id mapping with an hourly TTL."""
        if not self._available:
            self._mock_store[fingerprint] = incident_id
            return
        try:
            self._client.setex(f"dedup:{fingerprint}", ttl, incident_id)
        except Exception as exc:
            logger.warning("RedisDeduplicator.set failed: %s", exc)
