import json
import hashlib
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class CacheService:
    """Redis caching service for queries, embeddings and LLM responses."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def get_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _make_key(self, prefix: str, value: str) -> str:
        h = hashlib.md5(value.encode()).hexdigest()
        return f"rag:{prefix}:{h}"

    async def get(self, prefix: str, key: str) -> Optional[Any]:
        try:
            client = await self.get_client()
            cached = await client.get(self._make_key(prefix, key))
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("Cache get failed", error=str(e))
        return None

    async def set(self, prefix: str, key: str, value: Any, ttl: int = None) -> bool:
        try:
            client = await self.get_client()
            ttl = ttl or settings.redis_ttl_seconds
            await client.setex(
                self._make_key(prefix, key),
                ttl,
                json.dumps(value, default=str),
            )
            return True
        except Exception as e:
            logger.warning("Cache set failed", error=str(e))
            return False

    async def delete_by_prefix(self, prefix: str) -> int:
        """Delete all cache keys matching a prefix pattern."""
        try:
            client = await self.get_client()
            keys = await client.keys(f"rag:{prefix}:*")
            if keys:
                return await client.delete(*keys)
        except Exception as e:
            logger.warning("Cache delete failed", error=str(e))
        return 0

    async def invalidate_document(self, doc_id: str):
        """Invalidate all cache entries related to a document."""
        await self.delete_by_prefix(f"doc:{doc_id}")
        # Also clear query cache since results may have changed
        await self.delete_by_prefix("query")
        logger.info("Cache invalidated for document", doc_id=doc_id)

    async def get_query_result(self, query: str) -> Optional[dict]:
        return await self.get("query", query)

    async def set_query_result(self, query: str, result: dict) -> bool:
        return await self.set("query", query, result, ttl=1800)  # 30 min

    async def health_check(self) -> bool:
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except Exception:
            return False


_cache_service = None


def get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
