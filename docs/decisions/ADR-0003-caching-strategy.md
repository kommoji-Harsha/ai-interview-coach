# ADR-0003: LLM Response Caching

## Context
During evaluations, A/B testing, and standard usage, the exact same prompt with `temperature=0` is often sent to the LLM multiple times (especially for the Scorer and Feedback agents). This wastes time and incurs unnecessary API costs.

## Decision
We will implement **Redis-based Response Caching** at the LLM Gateway layer.
- Cache keys will be an SHA-256 hash of the canonicalized messages and model parameters.
- Caching will only apply to requests where `temperature == 0` (Scorer, Feedback).
- Interviewer calls (`temperature > 0`) bypass the cache to ensure variation.

## Consequences
- **Pros:** Drastically reduces cost and latency for repeat calls, accelerating eval runs.
- **Cons:** If a prompt's underlying context changes but the prompt text doesn't, stale data could be returned (mitigated by strict hashing of all inputs).
