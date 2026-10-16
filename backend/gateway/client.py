import time
from collections.abc import AsyncIterator

import structlog
from opentelemetry import trace
from pydantic import BaseModel

from backend.gateway.cache import ResponseCache
from backend.gateway.cost import calculate_cost, log_cost
from backend.gateway.models import CostRecord, LLMResult, Message, TranscriptionResult
from backend.gateway.retry import RetryPolicy, retry_with_backoff
from backend.gateway.routing import Router
from backend.observability.metrics import (
    LLM_CACHE_HITS_TOTAL,
    LLM_COST_USD_TOTAL,
    LLM_FALLBACKS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_RETRIES_TOTAL,
    LLM_TOKENS_TOTAL,
)
from backend.observability.tracing import get_tracer

logger = structlog.get_logger()
tracer = get_tracer("ai-interview-coach.gateway")


class LLMGateway:
    """THE only way to call an LLM in this codebase."""

    def __init__(
        self,
        router: Router,
        cache: ResponseCache,
        retry_policy: RetryPolicy | None = None,
    ):
        self._router = router
        self._cache = cache
        self._retry_policy = retry_policy or RetryPolicy()

    async def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: type[BaseModel] | None = None,
        agent_type: str = "unknown",
        session_id: str | None = None,
        prompt_version: str | None = None,
    ) -> LLMResult:
        with tracer.start_as_current_span("llm_gateway.complete") as span:
            if session_id:
                span.set_attribute("session.id", str(session_id))
            if prompt_version:
                span.set_attribute("agent.prompt_version", str(prompt_version))
            span.set_attribute("agent.type", str(agent_type))

            # 1. Check cache
            if cached_result := await self._cache.get(messages, model or "", temperature):
                span.set_attribute("llm.provider", cached_result.provider)
                span.set_attribute("llm.model", cached_result.model)
                span.set_attribute("llm.cache_hit", True)
                span.set_attribute("llm.cost_usd", 0.0)
                span.set_attribute("llm.latency_ms", 0)
                span.set_attribute("llm.retries", 0)
                span.set_attribute("llm.input_tokens", cached_result.input_tokens)
                span.set_attribute("llm.output_tokens", cached_result.output_tokens)

                LLM_CACHE_HITS_TOTAL.labels(agent_type=agent_type).inc()
                LLM_REQUESTS_TOTAL.labels(
                    provider=cached_result.provider,
                    model=cached_result.model,
                    status="success",
                ).inc()

                logger.info(
                    "llm_call_complete",
                    provider=cached_result.provider,
                    model=cached_result.model,
                    agent_type=agent_type,
                    session_id=session_id,
                    prompt_version=prompt_version,
                    latency_ms=0,
                    input_tokens=cached_result.input_tokens,
                    output_tokens=cached_result.output_tokens,
                    cost_usd=0.0,
                    cached=True,
                    retries=0,
                )

                await log_cost(
                    CostRecord(
                        provider=cached_result.provider,
                        model=cached_result.model,
                        agent_type=agent_type,
                        session_id=session_id,
                        cached=True,
                        success=True,
                    )
                )
                return cached_result

            # 2. Try each provider in the fallback chain
            chain = self._router.get_chain(agent_type)
            last_exc: Exception | None = None
            retries_total = 0

            for i, provider_cfg in enumerate(chain):
                effective_model = model or provider_cfg.model
                span.set_attribute("llm.provider", provider_cfg.provider.name)
                span.set_attribute("llm.model", effective_model)
                span.set_attribute("llm.cache_hit", False)

                start_time = time.perf_counter()
                try:
                    result = await retry_with_backoff(
                        lambda p=provider_cfg.provider, m=effective_model: p.complete(
                            messages=messages,
                            model=m,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            response_format=response_format,
                        ),
                        self._retry_policy,
                    )
                    duration = time.perf_counter() - start_time
                    latency_ms = int(duration * 1000)

                    # Calculate cost
                    result_cost = calculate_cost(
                        result.model, result.input_tokens, result.output_tokens
                    )

                    # Span attributes
                    span.set_attribute("llm.input_tokens", result.input_tokens)
                    span.set_attribute("llm.output_tokens", result.output_tokens)
                    span.set_attribute("llm.cost_usd", result_cost)
                    span.set_attribute("llm.latency_ms", latency_ms)
                    span.set_attribute("llm.retries", retries_total)

                    # Metrics
                    LLM_REQUEST_DURATION_SECONDS.labels(
                        provider=result.provider,
                        model=result.model,
                        agent_type=agent_type,
                    ).observe(duration)
                    LLM_TOKENS_TOTAL.labels(
                        provider=result.provider,
                        model=result.model,
                        direction="input",
                    ).inc(result.input_tokens)
                    LLM_TOKENS_TOTAL.labels(
                        provider=result.provider,
                        model=result.model,
                        direction="output",
                    ).inc(result.output_tokens)
                    LLM_COST_USD_TOTAL.labels(
                        provider=result.provider,
                        model=result.model,
                        agent_type=agent_type,
                    ).inc(result_cost)
                    LLM_REQUESTS_TOTAL.labels(
                        provider=result.provider,
                        model=result.model,
                        status="success",
                    ).inc()

                    # Structured logging
                    logger.info(
                        "llm_call_complete",
                        provider=result.provider,
                        model=result.model,
                        agent_type=agent_type,
                        session_id=session_id,
                        prompt_version=prompt_version,
                        latency_ms=latency_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result_cost,
                        cached=False,
                        retries=retries_total,
                    )

                    # Log cost record
                    await log_cost(
                        CostRecord(
                            provider=result.provider,
                            model=result.model,
                            agent_type=agent_type,
                            session_id=session_id,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            cost_usd=result_cost,
                            latency_ms=result.latency_ms,
                            retries=retries_total,
                            success=True,
                        )
                    )

                    # Cache result
                    await self._cache.set(messages, result.model, temperature, result)
                    return result

                except Exception as exc:
                    last_exc = exc
                    retries_total += 1
                    LLM_RETRIES_TOTAL.labels(
                        provider=provider_cfg.provider.name,
                        model=effective_model,
                    ).inc()
                    LLM_REQUESTS_TOTAL.labels(
                        provider=provider_cfg.provider.name,
                        model=effective_model,
                        status="error",
                    ).inc()

                    if i + 1 < len(chain):
                        next_provider = chain[i + 1].provider.name
                        LLM_FALLBACKS_TOTAL.labels(
                            from_provider=provider_cfg.provider.name,
                            to_provider=next_provider,
                        ).inc()

                    logger.warning(
                        "provider_failed",
                        provider=provider_cfg.provider.name,
                        model=effective_model,
                        error=str(exc),
                    )
                    continue

            # All providers failed
            span.record_exception(last_exc or Exception("All providers failed"))
            span.set_status(trace.StatusCode.ERROR, str(last_exc))
            logger.error("all_providers_failed", agent_type=agent_type)
            raise LLMUnavailableError(f"All LLM providers failed. Last error: {last_exc}")

    async def stream(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        agent_type: str = "unknown",
        session_id: str | None = None,
        prompt_version: str | None = None,
    ) -> AsyncIterator[str]:
        with tracer.start_as_current_span("llm_gateway.stream") as span:
            span.set_attribute("agent.type", str(agent_type))
            if session_id:
                span.set_attribute("session.id", str(session_id))
            if prompt_version:
                span.set_attribute("agent.prompt_version", str(prompt_version))

            chain = self._router.get_chain(agent_type)
            last_exc: Exception | None = None

            for provider_cfg in chain:
                effective_model = model or provider_cfg.model
                span.set_attribute("llm.provider", provider_cfg.provider.name)
                span.set_attribute("llm.model", effective_model)
                try:
                    async for token in provider_cfg.provider.stream(
                        messages=messages,
                        model=effective_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield token
                    return
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "stream_provider_failed",
                        provider=provider_cfg.provider.name,
                        error=str(exc),
                    )
                    continue

            span.record_exception(last_exc or Exception("All providers failed"))
            span.set_status(trace.StatusCode.ERROR, str(last_exc))
            raise LLMUnavailableError(
                f"All LLM providers failed for streaming. Last error: {last_exc}"
            )

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str = "en",
        model: str = "whisper-1",
        session_id: str | None = None,
    ) -> TranscriptionResult:
        with tracer.start_as_current_span("llm_gateway.transcribe") as span:
            if session_id:
                span.set_attribute("session.id", str(session_id))
            span.set_attribute("llm.model", str(model))

            chain = self._router.get_chain("transcription")
            last_exc: Exception | None = None

            for provider_cfg in chain:
                try:
                    result = await retry_with_backoff(
                        lambda p=provider_cfg.provider: p.transcribe(
                            audio_bytes=audio_bytes,
                            filename=filename,
                            content_type=content_type,
                            model=model,
                            language=language,
                        ),
                        self._retry_policy,
                    )
                    cost_usd = (
                        (result.duration_seconds / 60.0) * 0.006
                        if result.duration_seconds > 0
                        else 0.0
                    )
                    span.set_attribute("llm.provider", result.provider)
                    span.set_attribute("llm.cost_usd", cost_usd)
                    span.set_attribute("llm.latency_ms", result.latency_ms)

                    await log_cost(
                        CostRecord(
                            provider=result.provider,
                            model=result.model,
                            agent_type="transcription",
                            session_id=session_id,
                            cost_usd=cost_usd,
                            latency_ms=result.latency_ms,
                            success=True,
                        )
                    )
                    return result
                except NotImplementedError:
                    continue
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "transcribe_provider_failed",
                        provider=provider_cfg.provider.name,
                        error=str(exc),
                    )
                    continue

            if "openai_compat" in self._router._providers:
                provider = self._router._providers["openai_compat"]
                try:
                    result = await retry_with_backoff(
                        lambda p=provider: p.transcribe(
                            audio_bytes=audio_bytes,
                            filename=filename,
                            content_type=content_type,
                            model=model,
                            language=language,
                        ),
                        self._retry_policy,
                    )
                    cost_usd = (
                        (result.duration_seconds / 60.0) * 0.006
                        if result.duration_seconds > 0
                        else 0.0
                    )
                    span.set_attribute("llm.provider", result.provider)
                    span.set_attribute("llm.cost_usd", cost_usd)
                    span.set_attribute("llm.latency_ms", result.latency_ms)

                    await log_cost(
                        CostRecord(
                            provider=result.provider,
                            model=result.model,
                            agent_type="transcription",
                            session_id=session_id,
                            cost_usd=cost_usd,
                            latency_ms=result.latency_ms,
                            success=True,
                        )
                    )
                    return result
                except NotImplementedError:
                    pass
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "transcribe_fallback_failed",
                        provider=provider.name,
                        error=str(exc),
                    )

            span.record_exception(last_exc or Exception("All transcription providers failed"))
            span.set_status(trace.StatusCode.ERROR, str(last_exc))
            logger.error("all_transcription_providers_failed")
            raise LLMUnavailableError(
                f"All transcription providers failed. Last error: {last_exc}"
            )


class LLMUnavailableError(Exception):
    """Raised when all LLM providers fail."""

    pass
