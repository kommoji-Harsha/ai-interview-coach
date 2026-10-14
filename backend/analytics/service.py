"""Analytics service for aggregating interview progress, score trends, and weak topics."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import structlog
from backend.analytics.models import (
    ProgressAnalyticsResponse,
    ReviewSchedule,
    ReviewScheduleResponse,
    ScoreTrendPoint,
    UpcomingReviewItem,
)
from backend.analytics.scheduler import SpacedRepetitionScheduler
from backend.db.models import Score, Session, Turn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class AnalyticsService:
    """Provides progress metrics, performance trends across dimensions, and review schedules."""

    @classmethod
    async def get_progress(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        days: int = 30,
        base_date: datetime | None = None,
    ) -> ProgressAnalyticsResponse:
        """Compute aggregate progress metrics over the requested timeframe.

        Args:
            db: Database session.
            user_id: Target user UUID.
            days: Lookback window in days (1 to 180).
            base_date: Reference end timestamp (defaults to current UTC time).

        Returns:
            ProgressAnalyticsResponse with score trend, dimension averages, and weak topics.
        """
        days = max(1, min(180, days))
        if base_date is None:
            base_date = datetime.now(UTC)
        elif base_date.tzinfo is None:
            base_date = base_date.replace(tzinfo=UTC)

        cutoff_date = base_date - timedelta(days=days)

        # Query all sessions for this user
        stmt_all_sessions = (
            select(Session).where(Session.user_id == user_id).order_by(Session.started_at.asc())
        )
        res_all = await db.execute(stmt_all_sessions)
        all_sessions = list(res_all.scalars().all())

        total_sessions = len(all_sessions)

        # Filter sessions within period
        period_sessions: list[Session] = []
        for s in all_sessions:
            s_date = s.started_at
            if s_date.tzinfo is None:
                s_date = s_date.replace(tzinfo=UTC)
            if s_date >= cutoff_date:
                period_sessions.append(s)

        sessions_this_period = len(period_sessions)

        if not all_sessions:
            return ProgressAnalyticsResponse(
                total_sessions=0,
                sessions_this_period=0,
                score_trend=[],
                dimension_averages={},
                strongest_topic=None,
                weakest_topic=None,
            )

        # Fetch all turns and scores for the user's sessions to compute trends & metrics
        session_ids = [s.id for s in all_sessions]
        stmt_turns = (
            select(Turn)
            .where(Turn.session_id.in_(session_ids))
            .order_by(Turn.session_id, Turn.turn_number.asc())
        )
        res_turns = await db.execute(stmt_turns)
        turns = list(res_turns.scalars().all())

        turns_by_session: dict[uuid.UUID, list[Turn]] = defaultdict(list)
        turn_lookup: dict[uuid.UUID, Turn] = {}
        for t in turns:
            turns_by_session[t.session_id].append(t)
            turn_lookup[t.id] = t

        turn_ids = [t.id for t in turns]
        scores_by_turn: dict[uuid.UUID, list[Score]] = defaultdict(list)
        if turn_ids:
            stmt_scores = select(Score).where(Score.turn_id.in_(turn_ids))
            res_scores = await db.execute(stmt_scores)
            for sc in res_scores.scalars().all():
                scores_by_turn[sc.turn_id].append(sc)

        # 1. Compute score trends across period sessions
        date_scores: dict[str, list[float]] = defaultdict(list)
        target_sessions = period_sessions if period_sessions else all_sessions
        for s in target_sessions:
            s_date = s.started_at
            if s_date.tzinfo is None:
                s_date = s_date.replace(tzinfo=UTC)
            date_str = s_date.strftime("%Y-%m-%d")

            # Determine overall score for session
            session_overall = s.overall_score
            if session_overall is None:
                # Compute average from turns' scores
                s_turn_scores: list[float] = []
                for t in turns_by_session.get(s.id, []):
                    for sc in scores_by_turn.get(t.id, []):
                        s_turn_scores.append(float(sc.score))
                if s_turn_scores:
                    session_overall = sum(s_turn_scores) / len(s_turn_scores)

            if session_overall is not None:
                date_scores[date_str].append(session_overall)

        score_trend: list[ScoreTrendPoint] = []
        for d in sorted(date_scores.keys()):
            avg_overall = sum(date_scores[d]) / len(date_scores[d])
            score_trend.append(ScoreTrendPoint(date=d, overall=round(avg_overall, 1)))

        # 2. Compute dimension averages (for target sessions)
        dim_scores: dict[str, list[float]] = defaultdict(list)
        target_session_ids = {s.id for s in target_sessions}
        for s_id in target_session_ids:
            for t in turns_by_session.get(s_id, []):
                for sc in scores_by_turn.get(t.id, []):
                    dim_key = sc.dimension.strip().lower()
                    dim_scores[dim_key].append(float(sc.score))

        dimension_averages: dict[str, float] = {}
        for dim, vals in dim_scores.items():
            if vals:
                dimension_averages[dim] = round(sum(vals) / len(vals), 1)

        # 3. Detect strongest and weakest topics
        topic_scores: dict[str, list[float]] = defaultdict(list)
        for s_id in target_session_ids:
            s_turns = turns_by_session.get(s_id, [])
            turn_num_map = {t.turn_number: t for t in s_turns}

            for t in s_turns:
                t_scores = scores_by_turn.get(t.id, [])
                if not t_scores:
                    continue

                topic: str | None = t.topic
                if not topic and t.role == "candidate":
                    prev_turn = turn_num_map.get(t.turn_number - 1)
                    if prev_turn and prev_turn.topic:
                        topic = prev_turn.topic

                if topic:
                    topic_clean = topic.strip().lower()
                    for sc in t_scores:
                        topic_scores[topic_clean].append(float(sc.score))

        strongest_topic: str | None = None
        weakest_topic: str | None = None

        if topic_scores:
            topic_averages = {top: sum(scs) / len(scs) for top, scs in topic_scores.items() if scs}
            if topic_averages:
                sorted_topics = sorted(topic_averages.items(), key=lambda x: x[1])
                weakest_topic = sorted_topics[0][0]
                strongest_topic = sorted_topics[-1][0]

        return ProgressAnalyticsResponse(
            total_sessions=total_sessions,
            sessions_this_period=sessions_this_period,
            score_trend=score_trend,
            dimension_averages=dimension_averages,
            strongest_topic=strongest_topic,
            weakest_topic=weakest_topic,
        )

    @classmethod
    async def get_review_schedule(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        base_date: datetime | None = None,
    ) -> ReviewScheduleResponse:
        """Fetch upcoming scheduled reviews for the user, auto-queueing weak areas if needed.

        Args:
            db: Database session.
            user_id: User UUID.
            base_date: Optional reference datetime for queueing.

        Returns:
            ReviewScheduleResponse containing upcoming review items.
        """
        # Query pending reviews for this user
        stmt = (
            select(ReviewSchedule)
            .where(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.status == "pending",
            )
            .order_by(ReviewSchedule.scheduled_at.asc())
        )
        res = await db.execute(stmt)
        items = list(res.scalars().all())

        # If no pending items exist, scan recent completed sessions to queue any unqueued weak areas
        if not items:
            stmt_sessions = (
                select(Session)
                .where(
                    Session.user_id == user_id,
                    Session.status == "completed",
                )
                .order_by(Session.started_at.desc())
                .limit(5)
            )
            res_sess = await db.execute(stmt_sessions)
            recent_sessions = list(res_sess.scalars().all())
            for session in recent_sessions:
                await SpacedRepetitionScheduler.queue_weak_area_reviews(
                    db=db,
                    session=session,
                    base_date=base_date,
                )

            # Re-fetch pending reviews
            res = await db.execute(stmt)
            items = list(res.scalars().all())

        upcoming: list[UpcomingReviewItem] = []
        for item in items:
            dt = item.scheduled_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            # Format ISO 8601 UTC string (e.g., 2024-06-18T09:00:00Z)
            iso_utc = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            upcoming.append(
                UpcomingReviewItem(
                    session_id=str(item.session_id),
                    scheduled_at=iso_utc,
                    topic=item.topic,
                    reason=item.reason,
                )
            )

        return ReviewScheduleResponse(upcoming=upcoming)
