import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionConfig(BaseModel):
    difficulty: str = "auto"  # auto, easy, medium, hard
    max_turns: int = Field(default=10, ge=1, le=30)
    focus_topics: list[str] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    resume_text: str = Field(
        default="", description="Plain text resume (Phase 1: inline text instead of resume_id)"
    )
    jd_text: str = Field(
        default="", description="Plain text JD (Phase 1: inline text instead of jd_id)"
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
    content: str = Field(min_length=1)


class RespondResponse(BaseModel):
    turn_number: int
    role: str = "interviewer"
    content: str
    topic: str
    difficulty: int
    topics_covered: list[str]
    turns_remaining: int
