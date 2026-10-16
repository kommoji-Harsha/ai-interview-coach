"""Cost and latency computation metrics for LLM evaluation runs."""

import math
from typing import Any

# Pricing per million tokens (standard Gemini Flash baseline)
DEFAULT_INPUT_COST_PER_MILLION = 0.15
DEFAULT_OUTPUT_COST_PER_MILLION = 0.60


def estimate_token_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_rate_per_million: float = DEFAULT_INPUT_COST_PER_MILLION,
    output_rate_per_million: float = DEFAULT_OUTPUT_COST_PER_MILLION,
) -> float:
    """Calculate LLM cost in USD based on token counts."""
    input_cost = (prompt_tokens / 1_000_000.0) * input_rate_per_million
    output_cost = (completion_tokens / 1_000_000.0) * output_rate_per_million
    return round(input_cost + output_cost, 6)


def calculate_percentile(data: list[float], percentile: float) -> float:
    """Calculate the p-th percentile from a list of numeric values (0 <= percentile <= 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


def compute_cost_metrics(
    records: list[dict[str, Any]],
    total_answers: int,
) -> dict[str, float | int]:
    """Compute aggregate cost, token counts, and latency percentiles.

    Args:
        records: List of execution records containing 'latency_ms', 'cost_usd',
                 'prompt_tokens', 'completion_tokens'.
        total_answers: Number of distinct answers/cases evaluated.

    Returns:
        Dictionary with total_cost_usd, cost_per_answer_usd, latency_p50_ms, latency_p95_ms, total_tokens.
    """
    if not records:
        return {
            "total_cost_usd": 0.0,
            "cost_per_answer_usd": 0.0,
            "total_tokens": 0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "latency_mean_ms": 0.0,
        }

    total_cost = sum(r.get("cost_usd", 0.0) for r in records)
    total_tokens = sum(
        r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in records
    )
    latencies = [float(r.get("latency_ms", 0.0)) for r in records if "latency_ms" in r]

    ans_count = max(total_answers, 1)
    cost_per_answer = total_cost / ans_count

    return {
        "total_cost_usd": round(total_cost, 6),
        "cost_per_answer_usd": round(cost_per_answer, 6),
        "total_tokens": total_tokens,
        "latency_p50_ms": round(calculate_percentile(latencies, 50.0), 2)
        if latencies
        else 0.0,
        "latency_p95_ms": round(calculate_percentile(latencies, 95.0), 2)
        if latencies
        else 0.0,
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2)
        if latencies
        else 0.0,
    }
