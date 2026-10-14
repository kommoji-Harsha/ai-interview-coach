"""Tests for AnalyticsService and analytics HTTP endpoints per docs/api.md."""

import os
import uuid
from datetime import UTC, datetime

# Ensure required configuration is available for test suite before imports
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-min32chars")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.analytics.models import ReviewSchedule
from backend.analytics.router import router as analytics_router
from backend.analytics.service import AnalyticsService
from backend.config import get_settings
from backend.db.models import Base, Score, Session, Turn, User
from backend.db.session import get_db

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def analytics_db():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def test_app(analytics_db):
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1/analytics")

    # Dependency override for db
    async def _override_get_db():
        yield analytics_db

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture
async def api_client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def auth_headers(test_user):
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(test_user.id)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_user(analytics_db):
    user = User(
        email="analytics_user@example.com",
        hashed_password="hashed_pw",
        display_name="Analytics Tester",
    )
    analytics_db.add(user)
    await analytics_db.flush()
    return user


# ---------------------------------------------------------------------------
# AnalyticsService Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_empty_for_new_user(analytics_db, test_user):
    """Empty state returns zero sessions and empty metrics."""
    res = await AnalyticsService.get_progress(db=analytics_db, user_id=test_user.id, days=30)
    assert res.total_sessions == 0
    assert res.sessions_this_period == 0
    assert res.score_trend == []
    assert res.dimension_averages == {}
    assert res.strongest_topic is None
    assert res.weakest_topic is None


@pytest.mark.asyncio
async def test_progress_multi_session_trends_and_topics(analytics_db, test_user):
    """Calculates multi-session trends, dimension averages, and topic strengths."""
    base_date = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    date1 = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    date2 = datetime(2024, 6, 8, 10, 0, 0, tzinfo=UTC)
    date3 = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)

    # Session 1 on 2024-06-01: overall = 3.2
    s1 = Session(
        user_id=test_user.id,
        status="completed",
        overall_score=3.2,
        started_at=date1,
        ended_at=date1,
    )
    # Session 2 on 2024-06-08: overall = 3.5
    s2 = Session(
        user_id=test_user.id,
        status="completed",
        overall_score=3.5,
        started_at=date2,
        ended_at=date2,
    )
    # Session 3 on 2024-06-15: overall = 3.8
    s3 = Session(
        user_id=test_user.id,
        status="completed",
        overall_score=3.8,
        started_at=date3,
        ended_at=date3,
    )
    analytics_db.add_all([s1, s2, s3])
    await analytics_db.flush()

    # Add turns and scores to test dimensions and topic strengths
    # Turn in Session 1: behavioral (scores: communication=4, relevance=4 -> avg 4.0)
    t1_q = Turn(
        session_id=s1.id, turn_number=1, role="interviewer", topic="behavioral", content="Q1"
    )
    t1_a = Turn(session_id=s1.id, turn_number=2, role="candidate", content="A1")
    # Turn in Session 3: system-design (scores: technical_depth=2, relevance=3 -> avg 2.5)
    t3_q = Turn(
        session_id=s3.id, turn_number=1, role="interviewer", topic="system-design", content="Q3"
    )
    t3_a = Turn(session_id=s3.id, turn_number=2, role="candidate", content="A3")
    analytics_db.add_all([t1_q, t1_a, t3_q, t3_a])
    await analytics_db.flush()

    sc1 = Score(
        turn_id=t1_a.id,
        dimension="communication",
        score=4,
        evidence="Clear STAR",
        confidence=0.9,
        model_used="gemini",
    )
    sc2 = Score(
        turn_id=t1_a.id,
        dimension="relevance",
        score=4,
        evidence="Relevant",
        confidence=0.9,
        model_used="gemini",
    )
    sc3 = Score(
        turn_id=t3_a.id,
        dimension="technical_depth",
        score=2,
        evidence="Superficial",
        confidence=0.8,
        model_used="gemini",
    )
    sc4 = Score(
        turn_id=t3_a.id,
        dimension="relevance",
        score=3,
        evidence="Okay",
        confidence=0.8,
        model_used="gemini",
    )
    analytics_db.add_all([sc1, sc2, sc3, sc4])
    await analytics_db.flush()

    res = await AnalyticsService.get_progress(
        db=analytics_db, user_id=test_user.id, days=30, base_date=base_date
    )

    assert res.total_sessions == 3
    assert res.sessions_this_period == 3
    assert len(res.score_trend) == 3
    assert res.score_trend[0].date == "2024-06-01"
    assert res.score_trend[0].overall == 3.2
    assert res.score_trend[1].date == "2024-06-08"
    assert res.score_trend[1].overall == 3.5
    assert res.score_trend[2].date == "2024-06-15"
    assert res.score_trend[2].overall == 3.8

    assert res.dimension_averages["communication"] == 4.0
    assert res.dimension_averages["technical_depth"] == 2.0
    assert res.dimension_averages["relevance"] == 3.5

    assert res.strongest_topic == "behavioral"
    assert res.weakest_topic == "system-design"


@pytest.mark.asyncio
async def test_progress_days_window_filtering(analytics_db, test_user):
    """Sessions older than the days window are excluded from this period and trend."""
    base_date = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    old_date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)  # > 150 days ago
    recent_date = datetime(2024, 6, 14, 10, 0, 0, tzinfo=UTC)

    s_old = Session(
        user_id=test_user.id,
        status="completed",
        overall_score=2.0,
        started_at=old_date,
        ended_at=old_date,
    )
    s_new = Session(
        user_id=test_user.id,
        status="completed",
        overall_score=4.0,
        started_at=recent_date,
        ended_at=recent_date,
    )
    analytics_db.add_all([s_old, s_new])
    await analytics_db.flush()

    res = await AnalyticsService.get_progress(
        db=analytics_db, user_id=test_user.id, days=7, base_date=base_date
    )
    assert res.total_sessions == 2
    assert res.sessions_this_period == 1
    assert len(res.score_trend) == 1
    assert res.score_trend[0].date == "2024-06-14"
    assert res.score_trend[0].overall == 4.0


@pytest.mark.asyncio
async def test_review_schedule_retrieval(analytics_db, test_user):
    """Returns upcoming review items formatted per docs/api.md."""
    scheduled_date = datetime(2024, 6, 18, 9, 0, 0, tzinfo=UTC)
    session_id = uuid.uuid4()

    s = Session(id=session_id, user_id=test_user.id, status="completed")
    analytics_db.add(s)

    review = ReviewSchedule(
        user_id=test_user.id,
        session_id=session_id,
        topic="system-design",
        reason="Scored 2.5 — review recommended",
        scheduled_at=scheduled_date,
        status="pending",
    )
    analytics_db.add(review)
    await analytics_db.flush()

    res = await AnalyticsService.get_review_schedule(db=analytics_db, user_id=test_user.id)
    assert len(res.upcoming) == 1
    item = res.upcoming[0]
    assert item.session_id == str(session_id)
    assert item.scheduled_at == "2024-06-18T09:00:00Z"
    assert item.topic == "system-design"
    assert item.reason == "Scored 2.5 — review recommended"


# ---------------------------------------------------------------------------
# API Endpoint Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_progress_unauthorized(api_client):
    """GET /api/v1/analytics/progress returns 401 without auth token."""
    resp = await api_client.get("/api/v1/analytics/progress")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_progress_happy_path(api_client, auth_headers):
    """GET /api/v1/analytics/progress returns valid progress data."""
    resp = await api_client.get("/api/v1/analytics/progress?days=30", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_sessions" in data
    assert "sessions_this_period" in data
    assert "score_trend" in data
    assert "dimension_averages" in data
    assert "strongest_topic" in data
    assert "weakest_topic" in data


@pytest.mark.asyncio
async def test_get_progress_query_param_validation(api_client, auth_headers):
    """Invalid days param (e.g. > 180 or < 1) returns 422 validation error."""
    resp = await api_client.get("/api/v1/analytics/progress?days=200", headers=auth_headers)
    assert resp.status_code == 422

    resp_neg = await api_client.get("/api/v1/analytics/progress?days=0", headers=auth_headers)
    assert resp_neg.status_code == 422


@pytest.mark.asyncio
async def test_get_review_schedule_unauthorized(api_client):
    """GET /api/v1/analytics/review-schedule returns 401 without auth token."""
    resp = await api_client.get("/api/v1/analytics/review-schedule")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_review_schedule_happy_path(api_client, auth_headers):
    """GET /api/v1/analytics/review-schedule returns valid upcoming schedule."""
    resp = await api_client.get("/api/v1/analytics/review-schedule", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "upcoming" in data
    assert isinstance(data["upcoming"], list)
