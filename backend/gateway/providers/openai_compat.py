import json
import time
from collections.abc import AsyncIterator

import httpx
import structlog

from backend.gateway.models import LLMResult
from backend.gateway.providers.base import BaseLLMProvider

logger = structlog.get_logger()


class OpenAICompatProvider(BaseLLMProvider):
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    async def complete(
        self, messages, model, temperature=0.0, max_tokens=2048, response_format=None
    ) -> LLMResult:
        start = time.monotonic()
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = {"type": "json_object"}

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        usage = data.get("usage", {})

        return LLMResult(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            provider=self.name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=elapsed_ms,
            cached=False,
        )

    async def stream(
        self, messages, model, temperature=0.7, max_tokens=2048
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    if text := delta.get("content"):
                        yield text

    async def close(self):
        await self._client.aclose()
