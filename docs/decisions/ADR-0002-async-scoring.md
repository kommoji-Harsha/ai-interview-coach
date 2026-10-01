# ADR-0002: Async Scoring Architecture

## Context
After a candidate submits an interview answer, the system needs to evaluate it across multiple rubric dimensions using an LLM. Scoring can take 3-8 seconds, which would block the interview flow if done synchronously.

## Options Considered
1. **Inline / Synchronous Scoring:** Wait for the Scorer LLM call to finish before returning the next question.
2. **Background Worker / Async Scoring:** Return the next question immediately; score the answer in the background.

## Decision
We will use **Async Scoring via a Background Worker**.
- When an answer is received, the Orchestrator dispatches a background task to the worker queue.
- The Orchestrator immediately calls the Interviewer agent to generate the next question.
- Scores are calculated out-of-band and stored in the database. The frontend polls or uses SSE to retrieve scores when ready.

## Consequences
- **Pros:** Fast UX. The candidate never waits for the scorer, keeping the interview conversational.
- **Cons:** Increased system complexity (requires a task queue like Redis/Arq).
