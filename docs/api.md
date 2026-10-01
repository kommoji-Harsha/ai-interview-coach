# API Contract — AI Interview Coach

> **Base URL:** `/api/v1`
> **Auth:** Bearer JWT in `Authorization` header (except `/auth/register` and `/auth/login`)
> **Content-Type:** `application/json` (except file uploads: `multipart/form-data`)

---

## Common Conventions

### Error Format (all endpoints)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [
      {"field": "email", "reason": "invalid format"}
    ]
  }
}
```

| HTTP Status | Code | Meaning |
|-------------|------|---------|
| 400 | `VALIDATION_ERROR` | Bad input |
| 401 | `UNAUTHORIZED` | Missing or expired token |
| 403 | `FORBIDDEN` | Valid token, insufficient permissions |
| 404 | `NOT_FOUND` | Resource doesn't exist or not owned by user |
| 409 | `CONFLICT` | Duplicate resource (e.g., email already registered) |
| 422 | `UNPROCESSABLE` | Input understood but semantically invalid |
| 429 | `RATE_LIMITED` | Too many requests; `Retry-After` header set |
| 500 | `INTERNAL_ERROR` | Server fault |
| 502 | `LLM_UNAVAILABLE` | All LLM providers failed |

### Pagination (list endpoints)

Query params: `?cursor=<opaque>&limit=<int, default 20, max 100>`

Response wrapper:
```json
{
  "items": [...],
  "next_cursor": "abc123" | null
}
```

### Timestamps

All timestamps are ISO 8601 UTC strings: `"2024-06-15T09:30:00Z"`

---

## Auth

### `POST /auth/register`

**Rate limit:** 5 req/min per IP

```json
// Request
{
  "email": "user@example.com",
  "password": "min8chars!",
  "display_name": "Jane Doe"
}

// Response 201
{
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "Jane Doe",
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "expires_at": "2024-06-15T10:30:00Z"
}
```

### `POST /auth/login`

**Rate limit:** 5 req/min per IP

```json
// Request
{ "email": "user@example.com", "password": "min8chars!" }

// Response 200
{
  "user_id": "uuid",
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "expires_at": "2024-06-15T10:30:00Z"
}
```

### `POST /auth/refresh`

```json
// Request
{ "refresh_token": "jwt..." }

// Response 200
{
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "expires_at": "2024-06-15T10:30:00Z"
}
```

### `DELETE /auth/me`

Deletes the user and **all** associated data (cascading). Requires
password confirmation in request body.

```json
// Request
{ "password": "min8chars!" }

// Response 204  (no content)
```

---

## Resumes

### `POST /resumes`

**Content-Type:** `multipart/form-data`
**Rate limit:** 5 req/hour per user

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | Yes | PDF or DOCX, max 5 MB |
| `label` | string | No | User-given label |

```json
// Response 201
{
  "id": "uuid",
  "label": "SWE Resume 2024",
  "filename": "resume.pdf",
  "char_count": 4200,
  "created_at": "2024-06-15T09:30:00Z"
}
```

### `GET /resumes`

Paginated list of user's resumes. Returns metadata only (no full text).

### `GET /resumes/{id}`

Returns full resume including extracted text.

```json
{
  "id": "uuid",
  "label": "SWE Resume 2024",
  "filename": "resume.pdf",
  "raw_text": "Jane Doe — Software Engineer ...",
  "char_count": 4200,
  "created_at": "2024-06-15T09:30:00Z"
}
```

### `DELETE /resumes/{id}`

**Response:** 204

---

## Job Descriptions

### `POST /job-descriptions`

**Rate limit:** 10 req/hour per user

```json
// Request
{
  "company": "Acme Corp",
  "role_title": "Senior Backend Engineer",
  "raw_text": "We are looking for..."
}

// Response 201
{
  "id": "uuid",
  "company": "Acme Corp",
  "role_title": "Senior Backend Engineer",
  "char_count": 2100,
  "created_at": "2024-06-15T09:30:00Z"
}
```

### `GET /job-descriptions`
### `GET /job-descriptions/{id}`
### `DELETE /job-descriptions/{id}`

Same patterns as Resumes.

---

## Sessions

### `POST /sessions`

Starts a new mock interview session.
**Rate limit:** 10 req/hour per user

```json
// Request
{
  "resume_id": "uuid",
  "jd_id": "uuid",
  "config": {
    "difficulty": "auto" | "easy" | "medium" | "hard",
    "max_turns": 10,
    "focus_topics": ["system-design", "behavioral"]  // optional
  }
}

// Response 201
{
  "id": "uuid",
  "status": "active",
  "resume_id": "uuid",
  "jd_id": "uuid",
  "config": { ... },
  "first_question": {
    "turn_number": 1,
    "content": "Tell me about a time you led a project...",
    "topic": "behavioral",
    "difficulty": 2
  },
  "started_at": "2024-06-15T09:30:00Z"
}
```

### `GET /sessions`

Paginated list of user's sessions with summary info (status, score, date).

### `GET /sessions/{id}`

Full session detail including all turns.

```json
{
  "id": "uuid",
  "status": "active" | "completed" | "abandoned",
  "resume_id": "uuid",
  "jd_id": "uuid",
  "config": { ... },
  "turns": [
    {
      "turn_number": 1,
      "role": "interviewer",
      "content": "Tell me about...",
      "topic": "behavioral",
      "difficulty": 2,
      "created_at": "..."
    },
    {
      "turn_number": 2,
      "role": "candidate",
      "content": "In my previous role...",
      "created_at": "..."
    }
  ],
  "started_at": "...",
  "ended_at": null
}
```

### `POST /sessions/{id}/respond`

Submit candidate's answer. Returns the next interviewer question.

```json
// Request
{
  "content": "In my previous role at Acme, I led a team of five...",
  "audio_url": null  // optional, if voice input was used
}

// Response 200
{
  "turn_number": 3,
  "role": "interviewer",
  "content": "Interesting. How did you handle disagreements within the team?",
  "topic": "behavioral",
  "difficulty": 3,
  "topics_covered": ["behavioral"],
  "turns_remaining": 7
}
```

### `POST /sessions/{id}/respond` (streaming variant)

Same request, add `Accept: text/event-stream` header.

**SSE stream format:**

```
event: token
data: {"text": "Interesting"}

event: token
data: {"text": ". How"}

event: token
data: {"text": " did you"}

event: done
data: {"turn_number": 3, "topic": "behavioral", "difficulty": 3, "topics_covered": ["behavioral"], "turns_remaining": 7}
```

### `POST /sessions/{id}/end`

End the session early or after max turns. Triggers async feedback generation.

```json
// Response 200
{
  "status": "completed",
  "ended_at": "2024-06-15T10:00:00Z",
  "feedback_status": "generating"  // async; poll or use webhook
}
```

### `GET /sessions/{id}/scores`

Available after each turn is scored (async, typically < 5s).

```json
{
  "session_id": "uuid",
  "turns": [
    {
      "turn_number": 2,
      "answer_type": "attempted",
      "scores": [
        {
          "dimension": "communication",
          "score": 4,
          "evidence": "Candidate structured response using STAR method",
          "confidence": 0.85
        },
        {
          "dimension": "relevance",
          "score": 3,
          "evidence": "Answer addressed the question but lacked specifics",
          "confidence": 0.78
        }
      ]
    }
  ],
  "aggregate": {
    "communication": 3.8,
    "relevance": 3.5,
    "technical_depth": null,
    "overall": 3.6
  }
}
```

### `GET /sessions/{id}/feedback`

Available after session is completed and feedback is generated.

```json
{
  "session_id": "uuid",
  "status": "ready" | "generating" | "failed",
  "feedback": {
    "summary": "Strong communication skills with room for ...",
    "strengths": [
      "Clear STAR-method responses",
      "Good use of quantifiable results"
    ],
    "improvements": [
      "Provide more technical depth in system design answers",
      "Address edge cases proactively"
    ],
    "action_items": [
      "Practice system design with a 5-minute timer",
      "Prepare 3 examples of handling technical trade-offs"
    ],
    "recommended_topics": ["system-design", "trade-offs"]
  }
}
```

---

## Analytics

### `GET /analytics/progress`

Query params: `?days=30` (default 30, max 180)

```json
{
  "total_sessions": 12,
  "sessions_this_period": 5,
  "score_trend": [
    {"date": "2024-06-01", "overall": 3.2},
    {"date": "2024-06-08", "overall": 3.5},
    {"date": "2024-06-15", "overall": 3.8}
  ],
  "dimension_averages": {
    "communication": 3.9,
    "relevance": 3.6,
    "technical_depth": 3.2
  },
  "strongest_topic": "behavioral",
  "weakest_topic": "system-design"
}
```

### `GET /analytics/review-schedule`

```json
{
  "upcoming": [
    {
      "session_id": "uuid",
      "scheduled_at": "2024-06-18T09:00:00Z",
      "topic": "system-design",
      "reason": "Scored 2.5 — review recommended"
    }
  ]
}
```

---

## Voice

### `POST /voice/transcribe`

**Content-Type:** `multipart/form-data`
**Rate limit:** 30 req/min per user

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `audio` | file | Yes | WebM/WAV, max 25 MB, max 5 min |

```json
// Response 200
{
  "text": "In my previous role at Acme...",
  "duration_seconds": 45.2,
  "language": "en"
}
```

---

## Admin (internal, requires admin role)

### `POST /admin/eval-runs`

```json
// Request
{
  "prompt_version_id": "uuid",
  "golden_set": "interviewer"  // references evals/golden/{name}.jsonl
}

// Response 201
{
  "id": "uuid",
  "status": "running",
  "started_at": "2024-06-15T09:30:00Z"
}
```

### `GET /admin/eval-runs/{id}`

```json
{
  "id": "uuid",
  "status": "completed",
  "metrics": {
    "score_mae": 0.72,
    "score_consistency_std": 0.35,
    "feedback_coverage": 0.87,
    "latency_p50_ms": 1200,
    "latency_p95_ms": 3400,
    "total_cost_usd": 1.45
  },
  "started_at": "...",
  "completed_at": "...",
  "ci_run_id": "gh-actions-12345"
}
```
