# AGENTS.md: AI Interview Coach

## Project
Multi-agent interview coach. It runs mock interviews tailored to a resume
and job description, scores answers against a rubric, and includes an eval
harness that measures scorer accuracy and consistency.

## Stack
Python 3.11, FastAPI, SQLAlchemy, Postgres + pgvector, Pydantic v2,
Next.js (TypeScript) for the frontend, Docker, pytest, ruff.

## Repo layout
- backend/    FastAPI app, agents, orchestrator, LLM gateway
- frontend/   Next.js app
- evals/      golden set, runner, metrics, reports
- prompts/    versioned prompt files (never inline long prompts in code)
- infra/      Dockerfile, docker-compose, deploy notes
- docs/       api.md, architecture.md, screenshots/

## Working rules
1. Plan first. For any task bigger than one file, write a plan and wait
   for approval before writing code.
2. Small, focused changes. One phase or feature at a time.
3. Never commit secrets. Read config from environment variables.
   Keep .env.example up to date.
4. All LLM calls go through backend/llm_gateway. No direct SDK calls
   elsewhere. The gateway handles retries, model routing, and logging of
   tokens, latency and cost.
5. All LLM outputs used by code must be validated with Pydantic and
   retried on invalid output.
6. Do not modify files in evals/golden/ (human-labeled data).
7. Every feature needs tests. Mock LLM calls in unit tests.

## Code style
Type hints everywhere. Run `ruff check .` and `ruff format .` before
finishing. Run `pytest` and report the results.

## Definition of done
Tests pass, lint is clean, docs updated if an API changed, and a short
summary of what changed and how to run it.
