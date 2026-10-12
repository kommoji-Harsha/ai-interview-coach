import json
import time
from collections.abc import AsyncIterator

import httpx
import structlog

from backend.gateway.models import LLMResult, Message
from backend.gateway.providers.base import BaseLLMProvider

logger = structlog.get_logger()


def _to_gemini_contents(messages: list[Message]) -> tuple[str | None, list[dict]]:
    """Convert messages to Gemini format. Extract system instruction."""
    system_text = None
    contents = []
    for m in messages:
        if m.role == "system":
            system_text = m.content
        else:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})
    return system_text, contents


class GoogleProvider(BaseLLMProvider):
    name = "google"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=60.0)

    async def complete(
        self, messages, model, temperature=0.0, max_tokens=2048, response_format=None
    ) -> LLMResult:
        start = time.monotonic()
        system_text, contents = _to_gemini_contents(messages)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        if response_format:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        url = f"{self.BASE_URL}/models/{model}:generateContent?key={self.api_key}"
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})

        return LLMResult(
            content=text,
            model=model,
            provider=self.name,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=elapsed_ms,
            cached=False,
        )

    async def stream(
        self, messages, model, temperature=0.7, max_tokens=2048
    ) -> AsyncIterator[str]:
        system_text, contents = _to_gemini_contents(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        url = f"{self.BASE_URL}/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}"
        async with self._client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = json.loads(line[6:])
                    parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if text := part.get("text"):
                            yield text

    async def close(self):
        await self._client.aclose()
