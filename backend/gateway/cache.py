import hashlib
import json

import structlog
from redis.asyncio import Redis

from backend.gateway.models import LLMResult, Message

logger = structlog.get_logger()


class ResponseCache:
    def __init__(self, redis: Redis | None, default_ttl: int = 3600):
        self._redis = redis
        self._default_ttl = default_ttl

    def _cache_key(self, messages: list[Message], model: str, temperature: float) -> str | None:
        if temperature > 0:
            return None  # Only cache deterministic calls
        canonical = json.dumps(
            {"messages": [m.model_dump() for m in messages], "model": model},
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"llm:cache:{digest}"

    async def get(
        self, messages: list[Message], model: str, temperature: float
    ) -> LLMResult | None:
        if not self._redis:
            return None
        key = self._cache_key(messages, model, temperature)
        if not key:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                logger.debug("cache_hit", key=key[:20])
                result = LLMResult.model_validate_json(raw)
                result.cached = True
                return result
        except Exception:
            logger.warning("cache_get_error", exc_info=True)
        return None

    async def set(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        result: LLMResult,
        ttl: int | None = None,
    ) -> None:
        if not self._redis:
            return
        key = self._cache_key(messages, model, temperature)
        if not key:
            return
        try:
            await self._redis.set(key, result.model_dump_json(), ex=ttl or self._default_ttl)
            logger.debug("cache_set", key=key[:20])
        except Exception:
            logger.warning("cache_set_error", exc_info=True)
