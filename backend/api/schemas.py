import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionConfig(BaseModel):
    difficulty: str = "auto"  # auto, easy, medium, hard
    max_turns: int = Field(default=10, ge=1, le=30)
    focus_topics: list[str] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    resume_id: uuid.UUID | None = None
    jd_id: uuid.UUID | None = None
    resume_text: str = Field(
        default="",
        max_length=10_000,
        description="Plain text resume (max 10,000 characters)",
    )
    jd_text: str = Field(
        default="",
        max_length=5_000,
        description="Plain text job description (max 5,000 characters)",
    )
    config: SessionConfig = Field(default_factory=SessionConfig)


class QuestionResponse(BaseModel):
    turn_number: int
    content: str
    topic: str
    difficulty: int


class CreateSessionResponse(BaseModel):
    id: uuid.UUID
    status: str
    config: SessionConfig
    first_question: QuestionResponse
    started_at: datetime


class RespondRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5_000)
    audio_url: str | None = None


class RespondResponse(BaseModel):
    turn_number: int
    role: str = "interviewer"
    content: str
    topic: str
    difficulty: int
    topics_covered: list[str]
    turns_remaining: int


class TurnSummary(BaseModel):
    turn_number: int
    role: str
    content: str
    topic: str | None = None
    difficulty: int | None = None
    created_at: datetime | None = None


class SessionSummaryResponse(BaseModel):
    id: uuid.UUID
    status: str
    turn_count: int
    overall_score: float | None = None
    started_at: datetime
    ended_at: datetime | None = None


class SessionDetailResponse(BaseModel):
    id: uuid.UUID
    status: str
    resume_id: uuid.UUID | None = None
    jd_id: uuid.UUID | None = None
    config: SessionConfig
    turns: list[TurnSummary]
    turn_count: int
    overall_score: float | None = None
    started_at: datetime
    ended_at: datetime | None = None


class EndSessionResponse(BaseModel):
    status: str
    ended_at: datetime
    feedback_status: str = "generating"


class DimensionScoreItem(BaseModel):
    dimension: str
    score: int
    evidence: str
    confidence: float


class TurnScoreItem(BaseModel):
    turn_number: int
    answer_type: str = "attempted"
    scores: list[DimensionScoreItem]


class SessionScoresResponse(BaseModel):
    session_id: uuid.UUID
    turns: list[TurnScoreItem]
    aggregate: dict[str, float | None]


class FeedbackContent(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]
    action_items: list[str]
    recommended_topics: list[str]


class SessionFeedbackResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    feedback: FeedbackContent | None = None


class TranscribeResponse(BaseModel):
    text: str
    duration_seconds: float = 0.0
    language: str = "en"


# --- Resume Schemas ---


class ResumeMetadataResponse(BaseModel):
    id: uuid.UUID
    label: str
    filename: str
    char_count: int
    created_at: str


class ResumeDetailResponse(BaseModel):
    id: uuid.UUID
    label: str
    filename: str
    raw_text: str
    char_count: int
    created_at: str


class PaginatedResponse(BaseModel):
    items: list[dict | ResumeMetadataResponse | SessionSummaryResponse]
    next_cursor: str | None = None


# --- Auth Schemas ---


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=8)


class RefreshTokenRequest(BaseModel):
    refresh_token: str
