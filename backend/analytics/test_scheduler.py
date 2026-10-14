"""Unit tests for the SM-2 Spaced Repetition Scheduler with deterministic fixed dates."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.analytics.models import ReviewSchedule
from backend.analytics.scheduler import SpacedRepetitionScheduler
from backend.db.models import Base, Score, Session, Turn, User

# ---------------------------------------------------------------------------
# Pure Algorithmic SM-2 Tests with Fixed Dates
# ---------------------------------------------------------------------------


def test_sm2_first_review_with_fixed_date():
    """First successful review (n=0 -> n=1) sets interval to 1 day."""
    base_date = datetime(2024, 6, 15, 9, 0, 0, tzinfo=UTC)
    next_date, new_rep, new_int, new_ef = SpacedRepetitionScheduler.schedule_next_review(
        quality=4,
        repetitions=0,
        interval_days=1,
        ease_factor=2.5,
        base_date=base_date,
    )

    assert new_rep == 1
    assert new_int == 1
    assert new_ef == 2.5
    assert next_date == datetime(2024, 6, 16, 9, 0, 0, tzinfo=UTC)


def test_sm2_second_review_with_fixed_date():
    """Second successful review (n=1 -> n=2) sets interval to 6 days."""
    base_date = datetime(2024, 6, 16, 9, 0, 0, tzinfo=UTC)
    next_date, new_rep, new_int, new_ef = SpacedRepetitionScheduler.schedule_next_review(
        quality=4,
        repetitions=1,
        interval_days=1,
        ease_factor=2.5,
        base_date=base_date,
    )

    assert new_rep == 2
    assert new_int == 6
    assert new_ef == 2.5
    assert next_date == datetime(2024, 6, 22, 9, 0, 0, tzinfo=UTC)


def test_sm2_third_review_perfect_quality_with_fixed_date():
    """Third review with perfect quality (q=5) increases EF to 2.6 and scales interval."""
    base_date = datetime(2024, 6, 22, 9, 0, 0, tzinfo=UTC)
    # interval = round(6 * 2.6) = 16 days
    next_date, new_rep, new_int, new_ef = SpacedRepetitionScheduler.schedule_next_review(
        quality=5,
        repetitions=2,
        interval_days=6,
        ease_factor=2.5,
        base_date=base_date,
    )

    assert new_rep == 3
    assert new_ef == 2.6
    assert new_int == 16
    assert next_date == datetime(2024, 7, 8, 9, 0, 0, tzinfo=UTC)


def test_sm2_difficult_pass_decreases_ease_factor():
    """Passing with difficulty (q=3) decreases the ease factor while advancing interval."""
    base_date = datetime(2024, 6, 22, 9, 0, 0, tzinfo=UTC)
    # delta_ef = 0.1 - (2) * (0.08 + 2 * 0.02) = 0.1 - 0.24 = -0.14
    # new_ef = 2.5 - 0.14 = 2.36
    # interval = round(6 * 2.36) = 14 days
    next_date, new_rep, new_int, new_ef = SpacedRepetitionScheduler.schedule_next_review(
        quality=3,
        repetitions=2,
        interval_days=6,
        ease_factor=2.5,
        base_date=base_date,
    )

    assert new_rep == 3
    assert new_ef == 2.36
    assert new_int == 14
    assert next_date == datetime(2024, 7, 6, 9, 0, 0, tzinfo=UTC)


def test_sm2_failure_resets_repetitions_and_interval():
    """Quality below 3 resets repetition streak to 0 and interval to 1 day."""
    base_date = datetime(2024, 8, 1, 14, 30, 0, tzinfo=UTC)
    next_date, new_rep, new_int, new_ef = SpacedRepetitionScheduler.schedule_next_review(
        quality=2,
        repetitions=4,
        interval_days=25,
        ease_factor=2.4,
        base_date=base_date,
    )

    assert new_rep == 0
    assert new_int == 1
    assert new_ef < 2.4
    assert next_date == datetime(2024, 8, 2, 14, 30, 0, tzinfo=UTC)


def test_sm2_ease_factor_minimum_floor():
    """Ease factor never drops below 1.3 even under repeated failures."""
    ef = 1.35
    for _ in range(5):
        rep, interval, ef = SpacedRepetitionScheduler.calculate_sm2(
            quality=0,
            repetitions=0,
            interval_days=1,
            ease_factor=ef,
        )
    assert ef == 1.3
    assert interval == 1
    assert rep == 0


def test_identify_weak_topics():
    """Topics strictly below threshold are returned ordered from lowest to highest score."""
    topic_scores = {
        "system-design": [2.0, 3.0],  # avg = 2.5 -> weak
        "algorithms": [1.0, 2.0],  # avg = 1.5 -> weak (lowest)
        "behavioral": [4.0, 4.5],  # avg = 4.25 -> strong
        "networking": [3.0, 3.0],  # avg = 3.0 -> at threshold (not weak)
    }

    weak = SpacedRepetitionScheduler.identify_weak_topics(topic_scores, threshold=3.0)
    assert len(weak) == 2
    assert weak[0] == ("algorithms", 1.5)
    assert weak[1] == ("system-design", 2.5)


# ---------------------------------------------------------------------------
# Database Integration Tests with Fixed Dates
# ---------------------------------------------------------------------------


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_queue_weak_area_reviews_with_fixed_date(memory_db):
    """Weak topic questions in an interview session are queued with fixed review date."""
    fixed_session_date = datetime(2024, 6, 15, 9, 0, 0, tzinfo=UTC)

    # Setup User and Session
    user = User(
        email="test_scheduler@example.com",
        hashed_password="hash",
        display_name="Test Candidate",
    )
    memory_db.add(user)
    await memory_db.flush()

    session = Session(
        user_id=user.id,
        status="completed",
        started_at=fixed_session_date,
        ended_at=fixed_session_date,
    )
    memory_db.add(session)
    await memory_db.flush()

    # Turn 1: Interviewer asks System Design question
    turn1 = Turn(
        session_id=session.id,
        turn_number=1,
        role="interviewer",
        content="Design a URL shortener",
        topic="system-design",
        created_at=fixed_session_date,
    )
    memory_db.add(turn1)

    # Turn 2: Candidate answers System Design
    turn2 = Turn(
        session_id=session.id,
        turn_number=2,
        role="candidate",
        content="I will use a hash function...",
        created_at=fixed_session_date,
    )
    memory_db.add(turn2)

    # Turn 3: Interviewer asks Behavioral question
    turn3 = Turn(
        session_id=session.id,
        turn_number=3,
        role="interviewer",
        content="Tell me about a disagreement",
        topic="behavioral",
        created_at=fixed_session_date,
    )
    memory_db.add(turn3)

    # Turn 4: Candidate answers Behavioral
    turn4 = Turn(
        session_id=session.id,
        turn_number=4,
        role="candidate",
        content="In my previous job...",
        created_at=fixed_session_date,
    )
    memory_db.add(turn4)
    await memory_db.flush()

    # Scores for Turn 2 (System Design): scores 2 and 3 -> avg 2.5 (weak)
    score1 = Score(
        turn_id=turn2.id,
        dimension="technical_depth",
        score=2,
        evidence="Lacked specifics on database partitioning",
        confidence=0.8,
        model_used="gemini-2.0-flash",
    )
    score2 = Score(
        turn_id=turn2.id,
        dimension="scalability",
        score=3,
        evidence="Mentioned cache",
        confidence=0.8,
        model_used="gemini-2.0-flash",
    )
    # Scores for Turn 4 (Behavioral): scores 4 and 5 -> avg 4.5 (strong)
    score3 = Score(
        turn_id=turn4.id,
        dimension="communication",
        score=4,
        evidence="STAR method followed",
        confidence=0.9,
        model_used="gemini-2.0-flash",
    )
    score4 = Score(
        turn_id=turn4.id,
        dimension="relevance",
        score=5,
        evidence="Direct answer",
        confidence=0.95,
        model_used="gemini-2.0-flash",
    )
    memory_db.add_all([score1, score2, score3, score4])
    await memory_db.flush()

    # Queue weak areas with fixed base date
    queued = await SpacedRepetitionScheduler.queue_weak_area_reviews(
        db=memory_db,
        session=session,
        base_date=fixed_session_date,
        threshold=3.0,
    )

    assert len(queued) == 1
    item = queued[0]
    assert item.topic == "system-design"
    assert item.reason == "Scored 2.5 — review recommended"
    assert item.repetition_number == 0
    assert item.interval_days == 1
    assert item.scheduled_at == datetime(2024, 6, 16, 9, 0, 0, tzinfo=UTC)
    assert item.status == "pending"


@pytest.mark.asyncio
async def test_record_review_progression_fixed_dates(memory_db):
    """Review completion transitions to next interval with deterministic dates."""
    date_day1 = datetime(2024, 6, 15, 9, 0, 0, tzinfo=UTC)

    user = User(
        email="test_user2@example.com",
        hashed_password="hash",
        display_name="Candidate 2",
    )
    memory_db.add(user)
    await memory_db.flush()

    session = Session(user_id=user.id, status="completed", started_at=date_day1)
    memory_db.add(session)
    await memory_db.flush()

    # First pending review
    review = ReviewSchedule(
        user_id=user.id,
        session_id=session.id,
        topic="system-design",
        reason="Initial review",
        scheduled_at=date_day1,
        repetition_number=0,
        interval_days=1,
        ease_factor=2.5,
        status="pending",
    )
    memory_db.add(review)
    await memory_db.flush()

    # User completes review on 2024-06-15 with score 4
    next_review = await SpacedRepetitionScheduler.record_review_result(
        db=memory_db,
        review=review,
        quality=4,
        review_date=date_day1,
    )

    # Previous review is now marked completed
    assert review.status == "completed"
    assert review.completed_at == date_day1

    # Next review is scheduled 1 day later (first success: interval=1)
    assert next_review.status == "pending"
    assert next_review.repetition_number == 1
    assert next_review.interval_days == 1
    assert next_review.scheduled_at == datetime(2024, 6, 16, 9, 0, 0, tzinfo=UTC)

    # Next review taken on 2024-06-16 with score 4
    date_day2 = datetime(2024, 6, 16, 9, 0, 0, tzinfo=UTC)
    subsequent_review = await SpacedRepetitionScheduler.record_review_result(
        db=memory_db,
        review=next_review,
        quality=4,
        review_date=date_day2,
    )

    # Second success: interval = 6 days
    assert subsequent_review.repetition_number == 2
    assert subsequent_review.interval_days == 6
    assert subsequent_review.scheduled_at == datetime(2024, 6, 22, 9, 0, 0, tzinfo=UTC)
