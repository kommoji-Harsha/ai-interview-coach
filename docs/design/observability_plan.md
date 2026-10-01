# Observability Plan — AI Interview Coach

> Production concerns (cost, latency, security, observability) are first-class.
> — AGENTS.md

---

## Stack

| Layer | Tool | Why |
|-------|------|-----|
| **Traces** | OpenTelemetry SDK → Jaeger (or Tempo) | Vendor-neutral, free, distributed tracing |
| **Metrics** | OpenTelemetry SDK → Prometheus | Pull-based, battle-tested, free |
| **Dashboards** | Grafana | Connects to Prometheus + Jaeger, free |
| **Logs** | Python `structlog` → stdout → collected by Docker | Structured JSON, no extra infra |
| **Alerting** | Grafana Alerting (or Prometheus Alertmanager) | Co-located with dashboards |

> [!TIP]
> Everything runs in Docker Compose locally. In production, swap
> Jaeger/Prometheus for a managed service (Google Cloud Trace, Datadog)
> by changing the OTLP exporter endpoint — no code changes.

---

## 1. Tracing

### Span Hierarchy

Every API request produces a trace with this span tree:

```
[HTTP Request]  POST /api/v1/sessions/{id}/respond
 ├── [Middleware]  auth_middleware
 ├── [Safety]  input_screening
 │    ├── validate_input
 │    └── scan_for_injection
 ├── [Orchestrator]  process_turn
 │    ├── [DB]  save_candidate_turn
 │    ├── [Agent]  interviewer_agent.run
 │    │    ├── build_prompt
 │    │    ├── [Gateway]  llm_gateway.complete
 │    │    │    ├── cache_lookup          (attribute: cache_hit=true/false)
 │    │    │    ├── provider_call         (attribute: provider, model, tokens)
 │    │    │    └── cost_log
 │    │    └── validate_output            (attribute: retries=0)
 │    ├── [DB]  save_interviewer_turn
 │    └── [Worker]  enqueue_scoring_job
 └── [Response]  serialize_response
```

### Span Attributes (Key Fields)

| Attribute | Type | Example | On Spans |
|-----------|------|---------|----------|
| `user.id` | string | `"uuid"` | All |
| `session.id` | string | `"uuid"` | Orchestrator + below |
| `turn.number` | int | `3` | Agent + below |
| `llm.provider` | string | `"google"` | Gateway |
| `llm.model` | string | `"gemini-2.0-flash"` | Gateway |
| `llm.input_tokens` | int | `1250` | Gateway |
| `llm.output_tokens` | int | `380` | Gateway |
| `llm.cost_usd` | float | `0.0002` | Gateway |
| `llm.cache_hit` | bool | `false` | Gateway |
| `llm.retries` | int | `0` | Gateway |
| `agent.type` | string | `"interviewer"` | Agent |
| `agent.prompt_version` | string | `"v2"` | Agent |
| `safety.injection_detected` | bool | `false` | Safety |

> [!CAUTION]
> **NEVER put user content (resume text, answers, questions) in span
> attributes or logs.** Only metadata: IDs, counts, scores, latencies.
> This is a hard rule for PII safety.

### Implementation

```python
# backend/main.py
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def create_app():
    app = FastAPI()
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    RedisInstrumentor().instrument()
    return app

# backend/gateway/client.py
tracer = trace.get_tracer("ai-interview-coach.gateway")

async def complete(self, ...):
    with tracer.start_as_current_span("llm_gateway.complete") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("agent.type", agent_type)
        # ... call provider ...
        span.set_attribute("llm.input_tokens", result.input_tokens)
        span.set_attribute("llm.cost_usd", result.cost_usd)
```

---

## 2. Metrics

### LLM Metrics (emitted by Gateway)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `llm_request_duration_seconds` | Histogram | provider, model, agent_type | Latency distribution |
| `llm_tokens_total` | Counter | provider, model, direction (input/output) | Token consumption |
| `llm_cost_usd_total` | Counter | provider, model, agent_type | Spend tracking |
| `llm_requests_total` | Counter | provider, model, status (success/error) | Error rate |
| `llm_cache_hits_total` | Counter | agent_type | Cache effectiveness |
| `llm_retries_total` | Counter | provider, model | Retry burden |
| `llm_fallbacks_total` | Counter | from_provider, to_provider | Fallback frequency |

### API Metrics (auto-instrumented by FastAPI + OTLP)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `http_request_duration_seconds` | Histogram | method, path, status_code | Endpoint latency |
| `http_requests_total` | Counter | method, path, status_code | Traffic volume |
| `http_active_requests` | Gauge | method, path | Concurrency |

### Business Metrics (emitted by Orchestrator/Workers)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `sessions_created_total` | Counter | — | Usage growth |
| `sessions_completed_total` | Counter | — | Completion rate |
| `sessions_abandoned_total` | Counter | — | Drop-off tracking |
| `turns_per_session` | Histogram | — | Engagement depth |
| `scores_generated_total` | Counter | dimension | Scoring volume |
| `score_value` | Histogram | dimension | Score distribution |
| `feedback_generation_duration_seconds` | Histogram | — | Feedback latency |
| `eval_runs_total` | Counter | status (pass/fail) | Eval health |

### System Metrics (collected by Prometheus node exporter / cAdvisor)

| Metric | Source | Purpose |
|--------|--------|---------|
| CPU / Memory per container | cAdvisor | Resource planning |
| Postgres connections active | pg_exporter | Connection pool health |
| Redis memory usage | redis_exporter | Cache sizing |
| Postgres query duration | pg_exporter | DB bottleneck detection |

---

## 3. Dashboards

### Dashboard 1: LLM Operations

```
┌─────────────────────────────────────────────────┐
│  LLM Operations                                 │
├────────────────────┬────────────────────────────┤
│ Cost (USD/hour)    │ Latency p50/p95/p99        │
│ [line chart by     │ [line chart by provider]   │
│  agent_type]       │                            │
├────────────────────┼────────────────────────────┤
│ Error Rate (%)     │ Cache Hit Rate (%)         │
│ [line chart by     │ [line chart by agent_type] │
│  provider]         │                            │
├────────────────────┼────────────────────────────┤
│ Token Consumption  │ Fallback Events            │
│ [stacked bar:      │ [event log: from→to        │
│  input vs output]  │  with timestamps]          │
├────────────────────┼────────────────────────────┤
│ Retry Rate (%)     │ Top Models by Cost         │
│ [line chart]       │ [pie chart]                │
└────────────────────┴────────────────────────────┘
```

### Dashboard 2: API Health

```
┌─────────────────────────────────────────────────┐
│  API Health                                     │
├────────────────────┬────────────────────────────┤
│ Request Rate       │ Error Rate by Endpoint     │
│ [line chart,       │ [heatmap: endpoint × hour] │
│  req/sec]          │                            │
├────────────────────┼────────────────────────────┤
│ Latency p50/p95    │ Status Code Distribution   │
│ [by endpoint]      │ [stacked area: 2xx/4xx/5xx]│
├────────────────────┴────────────────────────────┤
│ Active Requests [gauge]    Rate-Limited [count]  │
└─────────────────────────────────────────────────┘
```

### Dashboard 3: Business Metrics

```
┌─────────────────────────────────────────────────┐
│  Business                                       │
├────────────────────┬────────────────────────────┤
│ Sessions/Day       │ Completion Rate (%)        │
│ [bar chart]        │ [line chart]               │
├────────────────────┼────────────────────────────┤
│ Avg Score Trend    │ Score Distribution          │
│ [line by dimension]│ [histogram: 1-5]           │
├────────────────────┼────────────────────────────┤
│ Turns/Session      │ Topics Practiced           │
│ [histogram]        │ [bar chart by category]    │
├────────────────────┴────────────────────────────┤
│ Registered Users [counter]   DAU [line chart]   │
└─────────────────────────────────────────────────┘
```

### Dashboard 4: System Resources

```
┌─────────────────────────────────────────────────┐
│  System Resources                               │
├────────────────────┬────────────────────────────┤
│ CPU by Container   │ Memory by Container        │
│ [line chart]       │ [line chart]               │
├────────────────────┼────────────────────────────┤
│ Postgres Conns     │ Redis Memory               │
│ [gauge + line]     │ [gauge + line]             │
├────────────────────┴────────────────────────────┤
│ Postgres Query Duration p95 [line chart]        │
└─────────────────────────────────────────────────┘
```

---

## 4. Alerting Rules

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| **LLM High Error Rate** | `llm_requests_total{status="error"}` > 5% for 5 min | 🔴 Critical | Page on-call; check provider status page |
| **LLM High Latency** | `llm_request_duration_seconds` p99 > 8s for 5 min | 🟡 Warning | Check provider; consider fallback |
| **API High Error Rate** | `http_requests_total{status=~"5.."}` > 2% for 5 min | 🔴 Critical | Check logs, deploy rollback |
| **API High Latency** | `http_request_duration_seconds` p99 > 5s for 5 min | 🟡 Warning | Profile slow endpoints |
| **Fallback Activated** | `llm_fallbacks_total` > 0 in 5 min | 🟡 Warning | Primary provider may be degraded |
| **Cost Spike** | `llm_cost_usd_total` rate > 2× daily average | 🟡 Warning | Possible abuse or prompt regression |
| **DB Connections Exhausted** | Active connections > 80% of pool | 🔴 Critical | Scale pool or investigate leaks |
| **Eval Regression** | CI eval gate fails | 🟡 Warning | PR blocked; review prompt changes |

### Notification Channels

| Channel | Used For |
|---------|----------|
| Slack / Discord webhook | All alerts |
| Email | Critical alerts |
| GitHub PR comment | Eval gate failures |

---

## 5. Structured Logging

```python
# All logs are structured JSON via structlog
import structlog

logger = structlog.get_logger()

# Example: gateway call
logger.info(
    "llm_call_complete",
    provider="google",
    model="gemini-2.0-flash",
    agent_type="scorer",
    session_id="uuid",
    latency_ms=1250,
    input_tokens=800,
    output_tokens=350,
    cost_usd=0.00016,
    cached=False,
    retries=0,
)
```

### Log Levels

| Level | Used For | Example |
|-------|----------|---------|
| `DEBUG` | Prompt construction details (dev only) | Prompt length, template used |
| `INFO` | Normal operations | LLM call complete, session created |
| `WARNING` | Degraded but functional | Fallback activated, low confidence score |
| `ERROR` | Failures requiring attention | All providers failed, validation exhausted |

### What Is NOT Logged

- Resume / JD text content
- Candidate answers
- Generated questions
- User email, phone, or any PII
- Full prompts (only prompt version ID + length)

---

## Infrastructure (Docker Compose)

```yaml
# infra/docker-compose.yml (observability services)
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./monitoring/dashboards:/var/lib/grafana/dashboards
      - ./monitoring/datasources.yml:/etc/grafana/provisioning/datasources/ds.yml
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
```
