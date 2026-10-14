"""API router exposing analytics and review schedule endpoints per docs/api.md."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.models import ProgressAnalyticsResponse, ReviewScheduleResponse
from backend.analytics.service import AnalyticsService
from backend.api.deps import get_current_user
from backend.db.models import User
from backend.db.session import get_db

router = APIRouter(tags=["analytics"])


@router.get(
    "/progress",
    response_model=ProgressAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user interview progress and score trends",
)
@router.get(
    "/analytics/progress",
    response_model=ProgressAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_progress(
    days: int = Query(default=30, ge=1, le=180, description="Number of days to analyze"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressAnalyticsResponse:
    """Return session counts, score trends, dimension averages, and weak topics."""
    return await AnalyticsService.get_progress(db=db, user_id=user.id, days=days)


@router.get(
    "/review-schedule",
    response_model=ReviewScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get upcoming spaced-repetition review schedule",
)
@router.get(
    "/analytics/review-schedule",
    response_model=ReviewScheduleResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_review_schedule(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewScheduleResponse:
    """Return scheduled upcoming reviews queued from candidate weak areas."""
    return await AnalyticsService.get_review_schedule(db=db, user_id=user.id)
