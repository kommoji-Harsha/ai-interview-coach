import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class LLMResult(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cached: bool = False


class CostRecord(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    agent_type: str = "unknown"
    session_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cached: bool = False
    retries: int = 0
    success: bool = True


class TranscriptionResult(BaseModel):
    text: str
    duration_seconds: float = 0.0
    language: str = "en"
    model: str = "whisper-1"
    provider: str = "openai_compat"
    latency_ms: int = 0
