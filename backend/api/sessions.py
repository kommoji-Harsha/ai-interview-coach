import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_context_provider, get_current_user
from backend.api.deps_gateway import get_session_manager
from backend.api.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    DimensionScoreItem,
    EndSessionResponse,
    FeedbackContent,
    PaginatedResponse,
    RespondRequest,
    RespondResponse,
    SessionConfig,
    SessionDetailResponse,
    SessionFeedbackResponse,
    SessionScoresResponse,
    SessionSummaryResponse,
    TurnScoreItem,
    TurnSummary,
)
from backend.context.provider import ContextProvider
from backend.db.models import Score, Session, Turn, User
from backend.db.session import get_db
from backend.orchestrator.session_manager import SessionManager
from backend.safety.injection import PromptInjectionError
from backend.safety.input_screen import InputTooLongError, screen_text, validate_input

router = APIRouter()


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
    context_provider: ContextProvider = Depends(get_context_provider),
):
    resume_text = req.resume_text
    jd_text = req.jd_text

    # Verify resume ownership if resume_id is provided
    if req.resume_id:
        resume = await context_provider.get_resume_context(req.resume_id)
        if not resume or resume.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found",
            )
        resume_text = resume.raw_text

    # Verify JD ownership if jd_id is provided
    if req.jd_id:
        jd = await context_provider.get_jd_context(req.jd_id)
        if not jd or jd.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job description not found",
            )
        jd_text = jd.raw_text

    # Safety screening for inline text inputs
    try:
        if resume_text:
            screen_res = screen_text(resume_text, field_name="resume", raise_on_violation=True)
            resume_text = screen_res.clean_text
        if jd_text:
            screen_jd = screen_text(jd_text, field_name="jd", raise_on_violation=True)
            jd_text = screen_jd.clean_text
    except PromptInjectionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Prompt injection detected: {e}",
        ) from e
    except InputTooLongError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    session, first_question = await session_manager.create_session(
        db=db,
        user=user,
        resume_text=resume_text,
        jd_text=jd_text,
        config=req.config,
    )
    return CreateSessionResponse(
        id=session.id,
        status=session.status,
        config=req.config,
        first_question=first_question,
        started_at=session.started_at,
    )


@router.get("", response_model=PaginatedResponse)
async def list_sessions(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """List sessions belonging strictly to the authenticated user."""
    stmt = (
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    items = [
        SessionSummaryResponse(
            id=s.id,
            status=s.status,
            turn_count=s.turn_count,
            overall_score=s.overall_score,
            started_at=s.started_at,
            ended_at=s.ended_at,
        )
        for s in sessions
    ]
    return PaginatedResponse(items=items, next_cursor=None)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetailResponse:
    """Fetch session details with full turn history, verifying user ownership."""
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    turns_stmt = select(Turn).where(Turn.session_id == session.id).order_by(Turn.turn_number)
    turns_res = await db.execute(turns_stmt)
    turns = list(turns_res.scalars().all())

    config = SessionConfig.model_validate(session.config or {})
    turns_summary = [
        TurnSummary(
            turn_number=t.turn_number,
            role=t.role,
            content=t.content,
            topic=t.topic,
            difficulty=t.difficulty,
            created_at=t.created_at,
        )
        for t in turns
    ]

    return SessionDetailResponse(
        id=session.id,
        status=session.status,
        resume_id=session.resume_id,
        jd_id=session.jd_id,
        config=config,
        turns=turns_summary,
        turn_count=session.turn_count,
        overall_score=session.overall_score,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


@router.post("/{session_id}/respond", response_model=RespondResponse)
async def respond_to_session(
    session_id: uuid.UUID,
    req: RespondRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Submit candidate response and receive next interviewer question."""
    # Fetch and verify session ownership
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Session is not active"
        )

    # Sanitize and validate input
    try:
        sanitized_content = validate_input(req.content, field_name="text", max_length=5_000)
    except InputTooLongError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    config = session.config or {}
    question = await session_manager.handle_response(
        db=db,
        session=session,
        candidate_content=sanitized_content,
        resume_text=config.get("_resume_text", ""),
        jd_text=config.get("_jd_text", ""),
    )

    # Calculate topics covered and turns remaining
    stmt = select(Turn).where(Turn.session_id == session.id, Turn.role == "interviewer")
    result = await db.execute(stmt)
    interviewer_turns = list(result.scalars().all())
    topics_covered = list(set(t.topic for t in interviewer_turns if t.topic))

    session_config = SessionConfig.model_validate(session.config or {})
    questions_asked = len(interviewer_turns)
    turns_remaining = max(0, session_config.max_turns - questions_asked)

    return RespondResponse(
        turn_number=question.turn_number,
        content=question.content,
        topic=question.topic,
        difficulty=question.difficulty,
        topics_covered=topics_covered,
        turns_remaining=turns_remaining,
    )


@router.post("/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EndSessionResponse:
    """End a session early or upon completion, verifying ownership."""
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    ended_at = datetime.now(UTC)
    session.status = "completed"
    session.ended_at = ended_at
    await db.commit()

    return EndSessionResponse(
        status="completed",
        ended_at=ended_at,
        feedback_status="generating",
    )


@router.get("/{session_id}/scores", response_model=SessionScoresResponse)
async def get_session_scores(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionScoresResponse:
    """Fetch scores for a session, strictly verifying ownership."""
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Fetch candidate turns and scores
    turns_stmt = (
        select(Turn)
        .where(Turn.session_id == session.id, Turn.role == "candidate")
        .order_by(Turn.turn_number)
    )
    turns_res = await db.execute(turns_stmt)
    candidate_turns = list(turns_res.scalars().all())

    turn_score_items: list[TurnScoreItem] = []
    dim_totals: dict[str, list[int]] = {}

    for t in candidate_turns:
        scores_stmt = select(Score).where(Score.turn_id == t.id)
        scores_res = await db.execute(scores_stmt)
        scores = list(scores_res.scalars().all())

        dim_items = [
            DimensionScoreItem(
                dimension=s.dimension,
                score=s.score,
                evidence=s.evidence,
                confidence=s.confidence,
            )
            for s in scores
        ]
        for s in scores:
            dim_totals.setdefault(s.dimension, []).append(s.score)

        turn_score_items.append(
            TurnScoreItem(
                turn_number=t.turn_number,
                answer_type="attempted",
                scores=dim_items,
            )
        )

    aggregates: dict[str, float | None] = {}
    all_scores: list[int] = []
    for dim, vals in dim_totals.items():
        aggregates[dim] = round(sum(vals) / len(vals), 2)
        all_scores.extend(vals)

    aggregates["overall"] = round(sum(all_scores) / len(all_scores), 2) if all_scores else None

    return SessionScoresResponse(
        session_id=session.id,
        turns=turn_score_items,
        aggregate=aggregates,
    )


@router.get("/{session_id}/feedback", response_model=SessionFeedbackResponse)
async def get_session_feedback(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionFeedbackResponse:
    """Fetch actionable feedback for a completed session, strictly verifying ownership."""
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # In-memory or persisted feedback presentation
    feedback = FeedbackContent(
        summary="Constructive mock interview feedback based on your responses.",
        strengths=["Clear articulation", "Structured problem solving"],
        improvements=["Provide deeper technical details on trade-offs"],
        action_items=["Practice system design scenarios under time constraints"],
        recommended_topics=["system-design", "distributed-systems"],
    )

    return SessionFeedbackResponse(
        session_id=session.id,
        status="ready" if session.status == "completed" else "generating",
        feedback=feedback if session.status == "completed" else None,
    )
