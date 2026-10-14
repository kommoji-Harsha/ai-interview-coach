from collections.abc import AsyncIterator

import structlog
from pydantic import BaseModel

from backend.gateway.cache import ResponseCache
from backend.gateway.cost import calculate_cost, log_cost
from backend.gateway.models import CostRecord, LLMResult, Message, TranscriptionResult
from backend.gateway.retry import RetryPolicy, retry_with_backoff
from backend.gateway.routing import Router

logger = structlog.get_logger()


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
    ) -> LLMResult:
        # 1. Check cache
        if cached_result := await self._cache.get(messages, model or "", temperature):
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

        for provider_cfg in chain:
            effective_model = model or provider_cfg.model
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

                # Calculate cost
                result_cost = calculate_cost(
                    result.model, result.input_tokens, result.output_tokens
                )

                # Log cost
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
                logger.warning(
                    "provider_failed",
                    provider=provider_cfg.provider.name,
                    model=effective_model,
                    error=str(exc),
                )
                continue

        # All providers failed
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
    ) -> AsyncIterator[str]:
        chain = self._router.get_chain(agent_type)
        last_exc: Exception | None = None

        for provider_cfg in chain:
            effective_model = model or provider_cfg.model
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
                    "stream_provider_failed", provider=provider_cfg.provider.name, error=str(exc)
                )
                continue

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

        logger.error("all_transcription_providers_failed")
        raise LLMUnavailableError(f"All transcription providers failed. Last error: {last_exc}")


class LLMUnavailableError(Exception):
    """Raised when all LLM providers fail."""

    pass
