"""Data models and Pydantic schemas for analytics and spaced repetition."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.models import Base, Session, User


class ReviewSchedule(Base):
    """Stores spaced repetition review items for users based on weak areas."""

    __tablename__ = "review_schedule"
    __table_args__ = (
        CheckConstraint("interval_days >= 1", name="chk_review_interval"),
        CheckConstraint("ease_factor >= 1.3", name="chk_review_ease_factor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False, index=True
    )
    repetition_number: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, server_default="2.5", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User")
    session: Mapped[Session] = relationship("Session")


class ScoreTrendPoint(BaseModel):
    """Overall score for a specific date in progress trend."""

    date: str = Field(description="ISO 8601 date string YYYY-MM-DD")
    overall: float = Field(description="Average overall score on this date")


class ProgressAnalyticsResponse(BaseModel):
    """Aggregate progress metrics over a specified period."""

    total_sessions: int = Field(description="Total interview sessions for the user")
    sessions_this_period: int = Field(
        description="Interview sessions within the requested timeframe"
    )
    score_trend: list[ScoreTrendPoint] = Field(
        default_factory=list, description="Chronological score trend points"
    )
    dimension_averages: dict[str, float] = Field(
        default_factory=dict, description="Average scores across rubric dimensions"
    )
    strongest_topic: str | None = Field(default=None, description="Topic with highest avg score")
    weakest_topic: str | None = Field(default=None, description="Topic with lowest avg score")


class UpcomingReviewItem(BaseModel):
    """An individual queued spaced-repetition review item."""

    session_id: str = Field(description="Source session ID as string")
    scheduled_at: str = Field(description="ISO 8601 UTC timestamp")
    topic: str = Field(description="Topic to review")
    reason: str = Field(description="Contextual explanation for review requirement")


class ReviewScheduleResponse(BaseModel):
    """Response containing upcoming scheduled reviews."""

    upcoming: list[UpcomingReviewItem] = Field(default_factory=list)


class SM2State(BaseModel):
    """Computed state for an SM-2 repetition iteration."""

    repetitions: int
    interval_days: int
    ease_factor: float
    next_review_date: datetime


class ReviewScheduleCreate(BaseModel):
    """Input payload to queue a review item."""

    model_config = ConfigDict(extra="ignore")

    session_id: uuid.UUID
    topic: str
    reason: str
    scheduled_at: datetime
    repetition_number: int = 0
    interval_days: int = 1
    ease_factor: float = 2.5
