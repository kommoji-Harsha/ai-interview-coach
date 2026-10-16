"""Prometheus metrics collectors and definitions."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# --- LLM Metrics (Gateway) ---

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "Duration of LLM provider requests in seconds",
    ["provider", "model", "agent_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0],
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total token consumption across providers and models",
    ["provider", "model", "direction"],
)

LLM_COST_USD_TOTAL = Counter(
    "llm_cost_usd_total",
    "Total cost of LLM calls in USD",
    ["provider", "model", "agent_type"],
)

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total LLM requests by provider, model, and status",
    ["provider", "model", "status"],
)

LLM_CACHE_HITS_TOTAL = Counter(
    "llm_cache_hits_total",
    "Total LLM cache hits",
    ["agent_type"],
)

LLM_RETRIES_TOTAL = Counter(
    "llm_retries_total",
    "Total LLM request retries due to errors",
    ["provider", "model"],
)

LLM_FALLBACKS_TOTAL = Counter(
    "llm_fallbacks_total",
    "Total provider fallback events",
    ["from_provider", "to_provider"],
)

# --- HTTP / API Metrics ---

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Duration of HTTP requests in seconds",
    ["method", "path", "status_code"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

HTTP_ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "Currently active HTTP requests",
    ["method", "path"],
)

# --- Business Metrics ---

SESSIONS_CREATED_TOTAL = Counter(
    "sessions_created_total",
    "Total number of mock interview sessions created",
)

SESSIONS_COMPLETED_TOTAL = Counter(
    "sessions_completed_total",
    "Total number of mock interview sessions completed",
)

SESSIONS_ABANDONED_TOTAL = Counter(
    "sessions_abandoned_total",
    "Total number of mock interview sessions abandoned",
)

TURNS_PER_SESSION = Histogram(
    "turns_per_session",
    "Distribution of turns per interview session",
    buckets=[1, 2, 4, 6, 8, 10, 15, 20],
)

SCORES_GENERATED_TOTAL = Counter(
    "scores_generated_total",
    "Total rubrics scores generated",
    ["dimension"],
)

SCORE_VALUE = Histogram(
    "score_value",
    "Distribution of rubric score values (1 to 5)",
    ["dimension"],
    buckets=[1.0, 2.0, 3.0, 4.0, 5.0],
)

FEEDBACK_GENERATION_DURATION_SECONDS = Histogram(
    "feedback_generation_duration_seconds",
    "Latency of feedback generation in seconds",
    buckets=[1.0, 2.5, 5.0, 10.0, 20.0, 30.0],
)

EVAL_RUNS_TOTAL = Counter(
    "eval_runs_total",
    "Total evaluation pipeline executions",
    ["status"],
)


def render_metrics(registry: CollectorRegistry = REGISTRY) -> bytes:
    """Export all registered metrics in Prometheus exposition format."""
    return generate_latest(registry)


def get_metrics_content_type() -> str:
    """Return the content type header for Prometheus scraping."""
    return CONTENT_TYPE_LATEST
