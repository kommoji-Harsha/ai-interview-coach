from unittest.mock import MagicMock

import httpx
import pytest

from backend.gateway.cache import ResponseCache
from backend.gateway.client import LLMGateway, LLMUnavailableError
from backend.gateway.cost import calculate_cost
from backend.gateway.models import LLMResult, Message
from backend.gateway.providers.base import BaseLLMProvider
from backend.gateway.retry import RetryPolicy, is_retryable, retry_with_backoff
from backend.gateway.routing import Router


class MockProvider(BaseLLMProvider):
    name = "mock"

    def __init__(self, result: LLMResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def complete(
        self, messages, model, temperature=0.0, max_tokens=2048, response_format=None
    ):
        if self._error:
            raise self._error
        return self._result or LLMResult(
            content="test response",
            model=model,
            provider=self.name,
            input_tokens=10,
            output_tokens=5,
            latency_ms=100,
        )

    async def stream(self, messages, model, temperature=0.7, max_tokens=2048):
        if self._error:
            raise self._error
        yield "Hello "
        yield "World"


@pytest.mark.asyncio
async def test_gateway_complete_success():
    provider = MockProvider()
    router = Router(
        providers={"mock": provider},
        fallback_chain=[("mock", "test-model")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache)

    result = await gateway.complete(
        messages=[Message(role="user", content="Hello")],
        agent_type="test",
    )
    assert result.content == "test response"
    assert result.provider == "mock"


@pytest.mark.asyncio
async def test_gateway_fallback():
    """When primary fails, should fall back to secondary."""
    primary = MockProvider(error=httpx.ConnectError("Connection refused"))
    secondary = MockProvider(
        result=LLMResult(
            content="fallback response",
            model="fallback-model",
            provider="secondary",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100,
        )
    )

    router = Router(
        providers={"primary": primary, "secondary": secondary},
        fallback_chain=[("primary", "model-1"), ("secondary", "model-2")],
    )
    cache = ResponseCache(redis=None)
    # Use 0 retries so fallback happens immediately
    gateway = LLMGateway(router=router, cache=cache, retry_policy=RetryPolicy(max_retries=0))

    result = await gateway.complete(
        messages=[Message(role="user", content="test")],
    )
    assert result.content == "fallback response"
    assert result.provider == "secondary"


@pytest.mark.asyncio
async def test_gateway_all_fail():
    """When all providers fail, should raise LLMUnavailableError."""
    provider = MockProvider(error=httpx.ConnectError("fail"))
    router = Router(
        providers={"mock": provider},
        fallback_chain=[("mock", "test-model")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache, retry_policy=RetryPolicy(max_retries=0))

    with pytest.raises(LLMUnavailableError):
        await gateway.complete(messages=[Message(role="user", content="test")])


@pytest.mark.asyncio
async def test_gateway_stream():
    provider = MockProvider()
    router = Router(
        providers={"mock": provider},
        fallback_chain=[("mock", "test-model")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache)

    tokens = []
    async for token in gateway.stream(
        messages=[Message(role="user", content="test")],
    ):
        tokens.append(token)
    assert tokens == ["Hello ", "World"]


def test_cost_calculation():
    cost = calculate_cost("gemini-2.0-flash", 1000, 500)
    expected = 1000 * 0.075 / 1_000_000 + 500 * 0.30 / 1_000_000
    assert abs(cost - expected) < 1e-10


def test_cost_unknown_model():
    cost = calculate_cost("unknown-model", 1000, 500)
    assert cost == 0.0


def test_is_retryable_429():
    response = MagicMock()
    response.status_code = 429
    exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=response)
    assert is_retryable(exc) is True


def test_is_retryable_400():
    response = MagicMock()
    response.status_code = 400
    exc = httpx.HTTPStatusError("bad request", request=MagicMock(), response=response)
    assert is_retryable(exc) is False


def test_is_retryable_connect_error():
    exc = httpx.ConnectError("Connection refused")
    assert is_retryable(exc) is True


@pytest.mark.asyncio
async def test_retry_succeeds_after_failure():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("fail")
        return "success"

    result = await retry_with_backoff(
        flaky, RetryPolicy(max_retries=3, base_delay=0.01, max_delay=0.02)
    )
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_cache_miss_and_set():
    cache = ResponseCache(redis=None)
    messages = [Message(role="user", content="hello")]
    result = await cache.get(messages, "model", 0.0)
    assert result is None  # No Redis, always miss
