from dataclasses import dataclass

import structlog

from backend.gateway.providers.base import BaseLLMProvider

logger = structlog.get_logger()


@dataclass
class ProviderConfig:
    provider: BaseLLMProvider
    model: str


class Router:
    def __init__(
        self, providers: dict[str, BaseLLMProvider], fallback_chain: list[tuple[str, str]]
    ):
        self._providers = providers
        self._fallback_chain = fallback_chain  # [(provider_name, model_name), ...]

    def get_chain(self, agent_type: str = "unknown") -> list[ProviderConfig]:
        """Return ordered list of (provider, model) to try."""
        chain = []
        for provider_name, model_name in self._fallback_chain:
            if provider_name in self._providers:
                chain.append(
                    ProviderConfig(
                        provider=self._providers[provider_name],
                        model=model_name,
                    )
                )
        return chain
