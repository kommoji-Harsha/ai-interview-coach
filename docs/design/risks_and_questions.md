# Risks, Assumptions & Open Questions

---

## Risks

### R1: LLM Output Quality Degrades Silently

| | |
|---|---|
| **Risk** | A provider model update changes output style/quality without notice, breaking Pydantic parsing or lowering score accuracy. |
| **Impact** | High — users get bad feedback; eval metrics regress without a code change. |
| **Mitigation** | CI eval gate runs on every PR AND on a nightly schedule against `main`. Nightly catch regressions caused by upstream model changes. Pin model versions where possible (e.g., `gemini-2.0-flash-001`). |
| **Detection** | Eval metrics drop; alert fires on nightly run failure. |

### R2: Prompt Injection Bypasses Safety Layer

| | |
|---|---|
| **Risk** | An attacker crafts a resume that slips past regex-based injection detection and manipulates LLM behavior. |
| **Impact** | Medium — inflated scores, leaked prompt text, or inappropriate questions. |
| **Mitigation** | Defense in depth (input screening + prompt architecture + output validation). Regex is the first layer, not the only one. The nonce-tagged XML structure and USER-only placement of untrusted text are the structural defenses. Regular red-team testing with new attack vectors. |
| **Residual risk** | Novel injection techniques will always be possible. Accept that no filter is perfect; the output validation (Pydantic) is the last line of defense. |

### R3: Cost Overruns

| | |
|---|---|
| **Risk** | A viral moment or abuse causes unexpectedly high LLM API spend. |
| **Impact** | High — financial. |
| **Mitigation** | Per-user rate limits. Cost-per-hour alert in Grafana. Daily budget cap in gateway config — if exceeded, reject new sessions with a friendly message. Caching reduces repeat-call costs. |
| **Worst case** | Set a hard monthly spend cap at the provider level (Google Cloud budget alerts, OpenAI usage limits). |

### R4: Scoring Inconsistency Erodes User Trust

| | |
|---|---|
| **Risk** | The same answer gets different scores on different runs, or scores feel arbitrary to the user. |
| **Impact** | Medium — users lose confidence in the tool. |
| **Mitigation** | Temperature=0 for scoring. Repeat-run consistency eval (σ < 0.5). Evidence requirement forces the model to justify scores. If consistency drops, switch to a stronger model for scoring (e.g., `gemini-2.5-pro`). |
| **Acceptance** | Some variance is inherent. Showing evidence alongside scores gives users a way to evaluate the score themselves. |

### R5: Latency Makes Conversations Feel Unnatural

| | |
|---|---|
| **Risk** | LLM calls take 3–8 seconds, making the interview feel sluggish. |
| **Impact** | Medium — poor UX. |
| **Mitigation** | SSE streaming so users see tokens arriving immediately. Async scoring (user doesn't wait for it). Use fast models (`gemini-2.0-flash`) for the interviewer. Show a typing indicator. |

### R6: Single-Developer Bus Factor

| | |
|---|---|
| **Risk** | This is a portfolio project built by one person. If you context-switch for weeks, it's hard to resume. |
| **Impact** | Low (it's a portfolio project) but affects completion. |
| **Mitigation** | ADRs document every non-obvious decision. Comprehensive `docs/api.md` means you can resume by reading the contract. Tests serve as living documentation. |

---

## Assumptions

### A1: LLM Quality Is Sufficient for Scoring

We assume that current-generation models (Gemini 2.0 Flash, GPT-4o-mini)
can reliably score interview answers on a 1–5 rubric with evidence.

**If wrong:** Scoring becomes the weakest link. Fallback: use a
stronger model (Gemini 2.5 Pro) for scoring only, accepting higher cost.
Or simplify to 3-point scale (poor / acceptable / strong).

### A2: Users Upload Real Resumes and JDs

The system is designed for genuine use. We don't optimize for adversarial
users submitting garbage text (beyond injection detection).

**If wrong:** Add content-quality checks: reject text < 100 chars,
reject text that doesn't look like a resume (simple heuristic or
classifier).

### A3: Postgres + pgvector Is Sufficient at Scale

We assume the user base stays < 10K active users with < 100K sessions.
At this scale, Postgres handles everything without sharding.

**If wrong:** pgvector HNSW indexes scale to ~1M vectors. Beyond that,
migrate embeddings to a dedicated vector DB (Pinecone, Weaviate). The
rest of the schema stays in Postgres.

### A4: One Worker Process Is Enough

Async scoring and feedback generation run in a single background worker
process (using a simple Redis queue or `arq`).

**If wrong:** Replace with Celery or a proper task queue. The worker
interface (enqueue / process) stays the same; only the transport changes.

### A5: JWT Auth Is Appropriate

JWTs are stateless and simple. We assume we don't need server-side
session revocation (e.g., "log out everywhere") as a launch feature.

**If wrong:** Add a Redis-backed token blacklist for revocation.
Or switch to opaque session tokens with Redis storage. ADR-0001 will
capture this decision.

### A6: Rubric Dimensions Are Fixed at Launch

We launch with 5 dimensions (communication, relevance, technical_depth,
problem_solving, examples). These are hardcoded in the scorer prompt and
golden set.

**If wrong:** Make dimensions configurable per JD or per session. This
means updating the scorer prompt template and golden set format. Defer
this unless users request it.

---

## Open Questions

### Q1: Which LLM Provider as Primary?

**Options:**
| Provider | Pros | Cons |
|----------|------|------|
| Google Gemini | Best cost/quality ratio, fast, generous free tier | Newer ecosystem |
| OpenAI | Most mature, best docs | Higher cost, no free tier |
| Anthropic | Best at following instructions | Highest cost |

**Recommendation:** Start with Gemini 2.0 Flash (cheapest, fast). The
gateway makes switching trivial. Decide after eval results.

### Q2: Voice Input — Build or Buy?

**Options:**
- **Whisper API (OpenAI):** \$0.006/min, high quality, simple
- **Google Cloud Speech-to-Text:** Similar pricing, keeps everything on GCP
- **Browser-side Whisper (whisper.cpp/WASM):** Free, but quality varies

**Recommendation:** Start with Whisper API for reliability. Add
browser-side as a progressive enhancement later. Voice is Phase 5 — can
defer the decision.

### Q3: How to Handle Very Short Answers?

If a candidate replies "I don't know" or gives a 5-word answer:
- Should the scorer still score it? (Probably yes, as 1/5)
- Should the interviewer move on or probe? (Probably probe once, then move on)
- Need a golden-set case for this.

**Decision needed before:** Phase 3 (Scoring).

### Q4: Session Timeout Behavior

If a user starts a session and disappears:
- When does it become "abandoned"? (30 min inactivity?)
- Should we send a reminder notification?
- Should abandoned sessions still generate feedback?

**Recommendation:** 30-min timeout → `abandoned`. No feedback for
abandoned sessions (< 3 turns isn't useful). No notifications at launch.

### Q5: Multi-Language Support

Should the system support non-English interviews?

**Recommendation:** No, not at launch. English only. The prompts,
rubric, and golden sets are all in English. Adding languages means
new prompts, new golden sets, and multilingual scoring validation.
Defer to post-launch.

### Q6: How Much of the Resume to Embed?

**Options:**
- Embed the full resume text as one vector
- Chunk by section (experience, skills, education) and embed each
- Embed full text + store parsed sections as JSONB

**Recommendation:** Option 3. One embedding for retrieval, parsed
sections in JSONB for structured access in prompts. Chunked embeddings
add complexity without clear value at this scale.

### Q7: Eval Golden Set — Who Labels?

For a portfolio project, you're the sole labeler. This creates bias.

**Mitigation:** Document your labeling rubric. When possible, have a
friend score 5 cases independently to check inter-rater agreement.
Acknowledge single-labeler limitation in docs.

### Q8: Free Tier / Demo Mode?

Should there be a way to try the app without registration?

**Options:**
- No auth required, limited to 1 session
- Guest token, data deleted after 24h
- Auth required, but free tier with 3 sessions/month

**Recommendation:** Auth required, 3 sessions/month free. Simplifies
the data model (every session has an owner). Good for a portfolio demo.

---

## Decision Log

| Question | Decision | Decided By | Date | ADR |
|----------|----------|------------|------|-----|
| Q1 | Gemini Flash as default, local fallback | Owner | 2024-06-15 | ADR-0004 |
| Q2 | Whisper API | Owner | 2024-06-15 | ADR-0005 |
| Q3 | "I don't know" is valid (`answer_type`) | Owner | 2024-06-15 | — |
| Q4 | 30-min timeout, no feedback | Owner | 2024-06-15 | — |
| Q5 | English only at launch | Owner | 2024-06-15 | — |
| Q6 | Full text embedding + JSONB sections | Owner | 2024-06-15 | — |
| Q7 | Self-labeled + 1 reviewer | Owner | 2024-06-15 | — |
| Q8 | No billing; daily rate-limits via Redis | Owner | 2024-06-15 | — |

> [!NOTE]
> Decisions should be recorded as ADRs in `docs/decisions/` once made.
> Each ADR captures context, options considered, decision, and consequences.
