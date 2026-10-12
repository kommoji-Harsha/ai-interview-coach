"""Gateway and session manager dependency injection."""

from backend.config import get_settings
from backend.gateway.cache import ResponseCache
from backend.gateway.client import LLMGateway
from backend.gateway.providers.google import GoogleProvider
from backend.gateway.providers.openai_compat import OpenAICompatProvider
from backend.gateway.retry import RetryPolicy
from backend.gateway.routing import Router
from backend.orchestrator.session_manager import SessionManager

_gateway_instance: LLMGateway | None = None
_session_manager_instance: SessionManager | None = None


def build_gateway() -> LLMGateway:
    """Build the LLM gateway with configured providers."""
    settings = get_settings()
    providers = {}

    # Register Google provider
    if settings.google_api_key:
        providers["google"] = GoogleProvider(api_key=settings.google_api_key)

    # Register OpenAI-compatible provider
    if settings.openai_api_key:
        providers["openai_compat"] = OpenAICompatProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_compat_base_url,
        )

    # Register local fallback (same OpenAI-compatible protocol)
    providers["local"] = OpenAICompatProvider(
        api_key="no-key",
        base_url=settings.local_base_url,
    )

    # Build fallback chain
    fallback_chain = [
        (settings.primary_provider, settings.primary_model),
        (settings.secondary_provider, settings.secondary_model),
        (settings.local_provider, settings.local_model),
    ]

    router = Router(providers=providers, fallback_chain=fallback_chain)
    cache = ResponseCache(
        redis=None,  # Redis connection set up during app startup
        default_ttl=settings.llm_cache_ttl_seconds,
    )
    retry_policy = RetryPolicy(
        max_retries=settings.llm_max_retries,
        base_delay=settings.llm_retry_base_delay,
        max_delay=settings.llm_retry_max_delay,
    )

    return LLMGateway(router=router, cache=cache, retry_policy=retry_policy)


def get_gateway() -> LLMGateway:
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = build_gateway()
    return _gateway_instance


def get_session_manager() -> SessionManager:
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager(gateway=get_gateway())
    return _session_manager_instance


def reset_gateway() -> None:
    """Reset singletons (useful for testing)."""
    global _gateway_instance, _session_manager_instance
    _gateway_instance = None
    _session_manager_instance = None
