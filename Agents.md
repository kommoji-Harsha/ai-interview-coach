# AGENTS.md: AI Interview Coach

## Project
Multi-user AI interview platform: adaptive mock interviews tailored to
a resume and job description, rubric scoring with evidence, progress
analytics, voice input, and an evaluation suite that measures LLM
quality. Production concerns (cost, latency, security, observability)
are first-class.

## Stack
Python 3.11, FastAPI, SQLAlchemy 2 + Alembic, Postgres + pgvector,
Redis, Pydantic v2, a background worker, Next.js (TypeScript), Docker,
pytest, ruff, GitHub Actions.

## Layout
backend/   api/, agents/, orchestrator/, gateway/, context/, safety/,
           analytics/, workers/, db/
frontend/  Next.js app
evals/     golden/, runner/, metrics/, reports/, prompt_ab/
prompts/   versioned prompt files (prompts/<agent>/v<N>.md)
infra/     Dockerfile(s), docker-compose, deploy, monitoring configs
docs/      api.md, architecture.md, decisions/ (ADRs), screenshots/

## Rules
1. Plan first for any change spanning more than one file.
2. Stay inside your assigned directory. Do not edit other lanes'
   directories; propose contract changes in docs/api.md instead.
3. All LLM calls go through backend/gateway. No direct SDK calls
   elsewhere. The gateway handles provider abstraction, retries,
   routing, caching, fallback, and logging of tokens, latency and cost.
4. Every LLM output used by code is validated with Pydantic and retried
   on invalid output.
5. Resume and job-description text is UNTRUSTED. It is isolated from
   instructions in prompts and screened by backend/safety.
6. Prompts live in prompts/ with version numbers; never inline long prompts.
7. Never modify evals/golden/ (human-labeled data).
8. Never commit secrets. Use env vars; keep .env.example current.
9. Database changes go through Alembic migrations.
10. Every feature has tests. Mock LLM calls in unit tests.
11. Record significant design choices as ADRs in docs/decisions/.

## Code style
Type hints everywhere. Run ruff check, ruff format, pytest (and the
frontend lint/tests) before finishing.

## Definition of done
Tests and lint pass, docs and OpenAPI updated, migrations included, and
a short summary of what changed and how to verify it.