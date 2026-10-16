"""Unit and integration tests for OpenTelemetry tracing, Prometheus metrics, and structured logging."""

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.api.schemas import SessionConfig
from backend.db.models import User
from backend.gateway.cache import ResponseCache
from backend.gateway.client import LLMGateway
from backend.gateway.models import LLMResult, Message
from backend.gateway.providers.base import BaseLLMProvider
from backend.gateway.retry import RetryPolicy
from backend.gateway.routing import Router
from backend.main import create_app
from backend.observability.logging import configure_logging, pii_scrubber
from backend.observability.tracing import init_tracer_provider
from backend.orchestrator.session_manager import SessionManager


class MockObservabilityProvider(BaseLLMProvider):
    name = "mock"

    def __init__(
        self,
        name: str = "mock",
        result: LLMResult | None = None,
        error: Exception | None = None,
    ):
        self.name = name
        self._result = result
        self._error = error

    async def complete(
        self, messages, model, temperature=0.0, max_tokens=2048, response_format=None
    ):
        if self._error:
            raise self._error
        return self._result or LLMResult(
            content='{"question": "What is Python?", "topic": "technical", "difficulty": 2}',
            model=model,
            provider=self.name,
            input_tokens=150,
            output_tokens=50,
            latency_ms=250,
        )

    async def stream(self, messages, model, temperature=0.7, max_tokens=2048):
        if self._error:
            raise self._error
        yield "Hello"


def test_pii_scrubber_redacts_sensitive_keys():
    """Verify that user content and credentials are redacted from structured log payloads."""
    raw_event = {
        "event": "llm_call_started",
        "session_id": "abc-123",
        "resume_text": "Candidate experience: Python, FastAPI...",
        "candidate_answer": "My answer is ...",
        "password": "supersecretpassword",
        "google_api_key": "AIzaSySecret",
        "latency_ms": 120,
    }
    scrubbed = pii_scrubber(None, "info", raw_event)

    assert scrubbed["session_id"] == "abc-123"
    assert scrubbed["latency_ms"] == 120
    assert scrubbed["resume_text"] == "[REDACTED]"
    assert scrubbed["candidate_answer"] == "[REDACTED]"
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["google_api_key"] == "[REDACTED]"


def test_configure_logging_runs_cleanly():
    """Verify logging configuration executes without errors."""
    configure_logging(log_level="DEBUG", json_logs=True)
    configure_logging(log_level="INFO", json_logs=False)


@pytest.mark.asyncio
async def test_metrics_endpoint_exposition():
    """Test the /metrics endpoint returns valid Prometheus text format."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        body = resp.text
        assert "llm_requests_total" in body
        assert "http_requests_total" in body


@pytest.mark.asyncio
async def test_gateway_tracing_and_metrics_on_success():
    """Verify OpenTelemetry spans and Prometheus metrics recorded on gateway completion."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    init_tracer_provider(processor_override=SimpleSpanProcessor(exporter))

    mock_provider = MockObservabilityProvider(name="google")
    router = Router(
        providers={"google": mock_provider},
        fallback_chain=[("google", "gemini-2.0-flash")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache)

    messages = [Message(role="user", content="Ask question")]
    session_id = str(uuid.uuid4())

    result = await gateway.complete(
        messages=messages,
        agent_type="interviewer",
        session_id=session_id,
        prompt_version="v1",
    )

    assert "question" in result.content

    # Verify spans captured in memory
    spans = exporter.get_finished_spans()
    gateway_spans = [s for s in spans if s.name == "llm_gateway.complete"]
    assert len(gateway_spans) >= 1

    span = gateway_spans[-1]
    attrs = span.attributes
    assert attrs["session.id"] == session_id
    assert attrs["agent.type"] == "interviewer"
    assert attrs["agent.prompt_version"] == "v1"
    assert attrs["llm.provider"] == "google"
    assert attrs["llm.model"] == "gemini-2.0-flash"
    assert attrs["llm.input_tokens"] == 150
    assert attrs["llm.output_tokens"] == 50
    assert attrs["llm.cache_hit"] is False
    assert attrs["llm.retries"] == 0
    assert attrs["llm.cost_usd"] > 0

    # Ensure no PII in span attributes
    for key, val in attrs.items():
        assert "resume" not in key.lower()
        assert "answer" not in key.lower()
        if isinstance(val, str):
            assert "Candidate" not in val


@pytest.mark.asyncio
async def test_gateway_cache_hit_tracing_and_metrics():
    """Verify span and metrics when LLM result is returned from cache."""
    exporter = InMemorySpanExporter()
    init_tracer_provider(processor_override=SimpleSpanProcessor(exporter))

    mock_redis = AsyncMock()
    # Cache hit response serialized
    cached_payload = LLMResult(
        content='{"question": "Cached question"}',
        model="gemini-2.0-flash",
        provider="google",
        input_tokens=100,
        output_tokens=40,
        latency_ms=0,
    ).model_dump_json()
    mock_redis.get.return_value = cached_payload

    cache = ResponseCache(redis=mock_redis)
    router = Router(
        providers={"google": MockObservabilityProvider(name="google")},
        fallback_chain=[("google", "gemini-2.0-flash")],
    )
    gateway = LLMGateway(router=router, cache=cache)

    messages = [Message(role="user", content="Ask question")]
    session_id = str(uuid.uuid4())

    cached_result = await gateway.complete(
        messages=messages,
        agent_type="interviewer",
        session_id=session_id,
        prompt_version="v1",
        temperature=0.0,
    )
    assert cached_result.content == '{"question": "Cached question"}'

    spans = exporter.get_finished_spans()
    cache_spans = [s for s in spans if s.name == "llm_gateway.complete"]
    assert len(cache_spans) >= 1
    attrs = cache_spans[-1].attributes
    assert attrs["llm.cache_hit"] is True
    assert attrs["llm.latency_ms"] == 0
    assert attrs["llm.cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_gateway_fallback_and_retry_metrics():
    """Verify retries and fallbacks are recorded when primary provider fails."""
    exporter = InMemorySpanExporter()
    init_tracer_provider(processor_override=SimpleSpanProcessor(exporter))

    primary_provider = MockObservabilityProvider(
        name="google", error=httpx.ConnectError("Primary failed")
    )
    secondary_provider = MockObservabilityProvider(
        name="secondary",
        result=LLMResult(
            content="Fallback answer",
            model="gpt-4o-mini",
            provider="secondary",
            input_tokens=80,
            output_tokens=30,
            latency_ms=400,
        ),
    )

    router = Router(
        providers={"google": primary_provider, "secondary": secondary_provider},
        fallback_chain=[("google", "gemini-2.0-flash"), ("secondary", "gpt-4o-mini")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache, retry_policy=RetryPolicy(max_retries=0))

    messages = [Message(role="user", content="Test fallback")]
    result = await gateway.complete(messages=messages, agent_type="interviewer")

    assert result.provider == "secondary"
    assert result.content == "Fallback answer"


@pytest.mark.asyncio
async def test_orchestrator_spans_and_metrics(db_session):
    """Verify orchestrator create_session emits OpenTelemetry spans and updates metrics."""
    exporter = InMemorySpanExporter()
    init_tracer_provider(processor_override=SimpleSpanProcessor(exporter))

    mock_provider = MockObservabilityProvider(
        name="google",
        result=LLMResult(
            content='{"question": "Tell me about a system you designed.", "topic": "system-design", "difficulty": 3}',
            model="gemini-2.0-flash",
            provider="google",
            input_tokens=200,
            output_tokens=40,
            latency_ms=300,
        ),
    )

    router = Router(
        providers={"google": mock_provider},
        fallback_chain=[("google", "gemini-2.0-flash")],
    )
    cache = ResponseCache(redis=None)
    gateway = LLMGateway(router=router, cache=cache)
    session_manager = SessionManager(gateway=gateway)

    user = User(
        email="candidate@example.com",
        hashed_password="hash",
        display_name="Candidate",
    )
    db_session.add(user)
    await db_session.flush()

    config = SessionConfig(difficulty="medium", max_turns=5, focus_topics=["system-design"])
    session, question_resp = await session_manager.create_session(
        db=db_session,
        user=user,
        resume_text="Senior backend engineer...",
        jd_text="Staff distributed systems role...",
        config=config,
    )

    assert question_resp.content == "Tell me about a system you designed."
    assert question_resp.topic == "system-design"

    spans = exporter.get_finished_spans()
    orchestrator_spans = [s for s in spans if s.name == "orchestrator.create_session"]
    assert len(orchestrator_spans) >= 1
    attrs = orchestrator_spans[-1].attributes
    assert attrs["session.id"] == str(session.id)
    assert attrs["user.id"] == str(user.id)
    assert attrs["turn.number"] == 1
