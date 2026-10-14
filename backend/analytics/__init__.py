"""Analytics package: metrics aggregation, score trends, and spaced-repetition scheduling."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-min32chars")

from backend.analytics.models import (
    ProgressAnalyticsResponse,
    ReviewSchedule,
    ReviewScheduleCreate,
    ReviewScheduleResponse,
    ScoreTrendPoint,
    SM2State,
    UpcomingReviewItem,
)
from backend.analytics.router import router
from backend.analytics.scheduler import SpacedRepetitionScheduler
from backend.analytics.service import AnalyticsService

__all__ = [
    "AnalyticsService",
    "ProgressAnalyticsResponse",
    "ReviewSchedule",
    "ReviewScheduleCreate",
    "ReviewScheduleResponse",
    "SM2State",
    "ScoreTrendPoint",
    "SpacedRepetitionScheduler",
    "UpcomingReviewItem",
    "router",
]
