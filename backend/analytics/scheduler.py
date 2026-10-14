"""Spaced repetition scheduler implementing the SM-2 algorithm.

Queues review items from candidate weak areas and projects future review dates
based on quality ratings.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.models import ReviewSchedule
from backend.db.models import Score, Session, Turn

logger = structlog.get_logger()


class SpacedRepetitionScheduler:
    """Calculates SM-2 review intervals and queues reviews for weak areas."""

    DEFAULT_EASE_FACTOR: float = 2.5
    MINIMUM_EASE_FACTOR: float = 1.3
    DEFAULT_WEAK_THRESHOLD: float = 3.0

    @classmethod
    def calculate_sm2(
        cls,
        quality: int | float,
        repetitions: int = 0,
        interval_days: int = 1,
        ease_factor: float = 2.5,
    ) -> tuple[int, int, float]:
        """Compute the next SM-2 parameters.

        Args:
            quality: Rating from 0 to 5. Scores >= 3 are considered passing.
            repetitions: Consecutive successful reviews count (starts at 0).
            interval_days: Current review interval in days.
            ease_factor: Easiness factor (minimum 1.3).

        Returns:
            tuple[repetitions, interval_days, ease_factor]
        """
        # Clamp quality to 0..5 integer
        q = max(0, min(5, int(round(quality))))

        # Update Ease Factor: EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        delta_ef = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
        new_ef = round(ease_factor + delta_ef, 2)
        if new_ef < cls.MINIMUM_EASE_FACTOR:
            new_ef = cls.MINIMUM_EASE_FACTOR

        if q < 3:
            # Review failed; reset repetition streak and restart interval at 1 day
            new_repetitions = 0
            new_interval = 1
        else:
            # Review passed
            if repetitions == 0:
                new_interval = 1
            elif repetitions == 1:
                new_interval = 6
            else:
                new_interval = max(1, int(round(interval_days * new_ef)))
            new_repetitions = repetitions + 1

        return new_repetitions, new_interval, new_ef

    @classmethod
    def schedule_next_review(
        cls,
        quality: int | float,
        repetitions: int = 0,
        interval_days: int = 1,
        ease_factor: float = 2.5,
        base_date: datetime | None = None,
    ) -> tuple[datetime, int, int, float]:
        """Calculate the next scheduled review datetime based on SM-2.

        Args:
            quality: Performance rating 0-5.
            repetitions: Current repetition count.
            interval_days: Current interval in days.
            ease_factor: Current ease factor.
            base_date: Reference datetime to compute interval from. Defaults to now (UTC).

        Returns:
            tuple[scheduled_at, repetitions, interval_days, ease_factor]
        """
        if base_date is None:
            base_date = datetime.now(UTC)
        elif base_date.tzinfo is None:
            base_date = base_date.replace(tzinfo=UTC)

        new_rep, new_int, new_ef = cls.calculate_sm2(
            quality=quality,
            repetitions=repetitions,
            interval_days=interval_days,
            ease_factor=ease_factor,
        )
        scheduled_at = base_date + timedelta(days=new_int)
        return scheduled_at, new_rep, new_int, new_ef

    @classmethod
    def identify_weak_topics(
        cls,
        topic_scores: dict[str, list[float]],
        threshold: float = DEFAULT_WEAK_THRESHOLD,
    ) -> list[tuple[str, float]]:
        """Identify topics with average score strictly below the threshold.

        Returns:
            List of (topic, average_score) tuples sorted by lowest score first.
        """
        weak_topics: list[tuple[str, float]] = []
        for topic, scores in topic_scores.items():
            if not scores:
                continue
            avg_score = sum(scores) / len(scores)
            if avg_score < threshold:
                weak_topics.append((topic, round(avg_score, 2)))

        weak_topics.sort(key=lambda item: item[1])
        return weak_topics

    @classmethod
    async def queue_weak_area_reviews(
        cls,
        db: AsyncSession,
        session: Session,
        base_date: datetime | None = None,
        threshold: float = DEFAULT_WEAK_THRESHOLD,
    ) -> list[ReviewSchedule]:
        """Analyze a session's turn scores and queue review items for weak topics.

        Args:
            db: Active database async session.
            session: Interview session to inspect.
            base_date: Starting date to calculate the first review interval (defaults to now).
            threshold: Score threshold below which a topic is flagged as weak.

        Returns:
            List of newly created or existing pending ReviewSchedule entries.
        """
        if base_date is None:
            base_date = session.ended_at or session.started_at or datetime.now(UTC)
        if base_date.tzinfo is None:
            base_date = base_date.replace(tzinfo=UTC)

        # Fetch turns for this session
        stmt_turns = (
            select(Turn).where(Turn.session_id == session.id).order_by(Turn.turn_number.asc())
        )
        res_turns = await db.execute(stmt_turns)
        turns = list(res_turns.scalars().all())

        # Map turns by number
        turn_by_number: dict[int, Turn] = {t.turn_number: t for t in turns}

        # Fetch scores for these turns
        turn_ids = [t.id for t in turns]
        if not turn_ids:
            return []

        stmt_scores = select(Score).where(Score.turn_id.in_(turn_ids))
        res_scores = await db.execute(stmt_scores)
        scores = list(res_scores.scalars().all())

        # Associate scores with topic
        topic_scores: dict[str, list[float]] = {}
        for score in scores:
            t = next((turn for turn in turns if turn.id == score.turn_id), None)
            if not t:
                continue

            topic: str | None = t.topic
            if not topic and t.role == "candidate":
                # Check previous interviewer turn for question topic
                prev_turn = turn_by_number.get(t.turn_number - 1)
                if prev_turn and prev_turn.topic:
                    topic = prev_turn.topic

            if topic:
                topic_clean = topic.strip().lower()
                topic_scores.setdefault(topic_clean, []).append(float(score.score))

        weak_topics = cls.identify_weak_topics(topic_scores, threshold=threshold)
        if not weak_topics:
            return []

        # Check existing pending reviews for this user & session to avoid duplication
        stmt_existing = select(ReviewSchedule).where(
            ReviewSchedule.user_id == session.user_id,
            ReviewSchedule.session_id == session.id,
            ReviewSchedule.status == "pending",
        )
        res_existing = await db.execute(stmt_existing)
        existing_items = list(res_existing.scalars().all())
        existing_topics = {item.topic.lower() for item in existing_items}

        new_reviews: list[ReviewSchedule] = []
        for topic, avg_score in weak_topics:
            if topic in existing_topics:
                continue

            # First interval for weak topic review is 1 day
            first_review_date = base_date + timedelta(days=1)
            reason = f"Scored {avg_score:.1f} — review recommended"

            review_entry = ReviewSchedule(
                user_id=session.user_id,
                session_id=session.id,
                topic=topic,
                reason=reason,
                scheduled_at=first_review_date,
                repetition_number=0,
                interval_days=1,
                ease_factor=cls.DEFAULT_EASE_FACTOR,
                status="pending",
            )
            db.add(review_entry)
            new_reviews.append(review_entry)

        if new_reviews:
            await db.flush()

        # Combine existing and new
        return existing_items + new_reviews

    @classmethod
    async def record_review_result(
        cls,
        db: AsyncSession,
        review: ReviewSchedule,
        quality: int | float,
        review_date: datetime | None = None,
    ) -> ReviewSchedule:
        """Process a completed review, update current record, and queue the next interval.

        Args:
            db: Database session.
            review: Current pending review.
            quality: Score achieved in the review (0-5).
            review_date: Date the review was taken (defaults to now).

        Returns:
            The newly scheduled ReviewSchedule entry for the next interval.
        """
        if review_date is None:
            review_date = datetime.now(UTC)
        elif review_date.tzinfo is None:
            review_date = review_date.replace(tzinfo=UTC)

        # Mark current review as completed
        review.status = "completed"
        review.completed_at = review_date

        # Calculate next SM-2 step
        next_date, next_rep, next_int, next_ef = cls.schedule_next_review(
            quality=quality,
            repetitions=review.repetition_number,
            interval_days=review.interval_days,
            ease_factor=review.ease_factor,
            base_date=review_date,
        )

        reason = (
            f"Review #{next_rep}: interval {next_int}d (last score: {quality})"
            if next_rep > 0
            else f"Review reset: interval {next_int}d (last score: {quality})"
        )

        next_review = ReviewSchedule(
            user_id=review.user_id,
            session_id=review.session_id,
            topic=review.topic,
            reason=reason,
            scheduled_at=next_date,
            repetition_number=next_rep,
            interval_days=next_int,
            ease_factor=next_ef,
            status="pending",
        )
        db.add(next_review)
        await db.flush()
        return next_review
