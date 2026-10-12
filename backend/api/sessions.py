import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.deps_gateway import get_session_manager
from backend.api.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    RespondRequest,
    RespondResponse,
)
from backend.db.models import Session, Turn, User
from backend.db.session import get_db
from backend.orchestrator.session_manager import SessionManager

router = APIRouter()


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
):
    session, first_question = await session_manager.create_session(
        db=db,
        user=user,
        resume_text=req.resume_text,
        jd_text=req.jd_text,
        config=req.config,
    )
    return CreateSessionResponse(
        id=session.id,
        status=session.status,
        config=req.config,
        first_question=first_question,
        started_at=session.started_at,
    )


@router.post("/{session_id}/respond", response_model=RespondResponse)
async def respond_to_session(
    session_id: uuid.UUID,
    req: RespondRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
):
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

    config = session.config or {}
    question = await session_manager.handle_response(
        db=db,
        session=session,
        candidate_content=req.content,
        resume_text=config.get("_resume_text", ""),
        jd_text=config.get("_jd_text", ""),
    )

    # Calculate topics covered and turns remaining
    stmt = select(Turn).where(Turn.session_id == session.id, Turn.role == "interviewer")
    result = await db.execute(stmt)
    interviewer_turns = list(result.scalars().all())
    topics_covered = list(set(t.topic for t in interviewer_turns if t.topic))

    from backend.api.schemas import SessionConfig

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
