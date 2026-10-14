from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel

from backend.gateway.models import LLMResult, Message, TranscriptionResult


class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: type[BaseModel] | None = None,
    ) -> LLMResult: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]: ...

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        model: str = "whisper-1",
        language: str = "en",
    ) -> TranscriptionResult:
        raise NotImplementedError(f"Provider {self.name} does not support audio transcription")
