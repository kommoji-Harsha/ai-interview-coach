import asyncio
import random
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    jitter: float = 0.5

    def get_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        jitter_amount = random.uniform(-self.jitter, self.jitter)
        return max(0.1, delay + jitter_amount)


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout))


async def retry_with_backoff(coro_factory, policy: RetryPolicy | None = None):
    """Retry an async callable with exponential backoff.
    coro_factory is a zero-arg callable that returns a coroutine each time."""
    policy = policy or RetryPolicy()
    last_exc = None
    for attempt in range(policy.max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt >= policy.max_retries or not is_retryable(exc):
                raise
            delay = policy.get_delay(attempt)
            logger.warning("llm_retry", attempt=attempt + 1, delay=delay, error=str(exc))
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
