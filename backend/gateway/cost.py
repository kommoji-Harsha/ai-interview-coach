import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gateway.models import CostRecord

logger = structlog.get_logger()

TOKEN_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.0-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 10.0 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "llama3.2": {"input": 0.0, "output": 0.0},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = TOKEN_PRICING.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])


async def log_cost(record: CostRecord, db: AsyncSession | None = None) -> None:
    """Log cost to structured log and optionally to DB."""
    logger.info(
        "llm_cost",
        provider=record.provider,
        model=record.model,
        agent_type=record.agent_type,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cost_usd=record.cost_usd,
        latency_ms=record.latency_ms,
        cached=record.cached,
        retries=record.retries,
        success=record.success,
    )
    if db:
        from backend.db.models import LLMCostLog

        log_entry = LLMCostLog(
            provider=record.provider,
            model=record.model,
            agent_type=record.agent_type,
            session_id=record.session_id,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cost_usd=record.cost_usd,
            latency_ms=record.latency_ms,
            cached=record.cached,
            retries=record.retries,
            success=record.success,
        )
        db.add(log_entry)
