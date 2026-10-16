import json

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import QuestionResponse, SessionConfig
from backend.db.models import Session, Turn, User
from backend.gateway.client import LLMGateway
from backend.gateway.models import Message
from backend.observability.metrics import SESSIONS_CREATED_TOTAL, TURNS_PER_SESSION
from backend.observability.tracing import get_tracer

logger = structlog.get_logger()
tracer = get_tracer("ai-interview-coach.orchestrator")

INTERVIEWER_SYSTEM_PROMPT = """You are an expert technical interviewer conducting a mock interview.
The candidate has provided their resume and the job description they are targeting.

Resume:
{resume_text}

Job Description:
{jd_text}

Difficulty level: {difficulty}
Focus topics: {focus_topics}

Instructions:
1. Ask one clear, specific interview question tailored to the candidate's background.
2. Adapt difficulty based on previous answers.
3. Cover the requested focus topics across the interview.
4. If this is the first question, start with a warm introduction and an appropriate opening question.
5. For follow-ups, build on the candidate's previous answer to probe deeper.

Respond ONLY with a JSON object (no markdown, no extra text):
{{"question": "your question", "topic": "behavioral|technical|system-design|coding", "difficulty": 1-5, "reasoning": "brief explanation"}}
"""


class SessionManager:
    """Manages interview session lifecycle and turn coordination."""

    def __init__(self, gateway: LLMGateway):
        self._gateway = gateway

    async def create_session(
        self,
        db: AsyncSession,
        user: User,
        resume_text: str,
        jd_text: str,
        config: SessionConfig,
    ) -> tuple[Session, QuestionResponse]:
        """Create a new interview session and generate the first question."""
        with tracer.start_as_current_span("orchestrator.create_session") as span:
            session = Session(
                user_id=user.id,
                config=config.model_dump(),
                status="active",
            )
            db.add(session)
            await db.flush()

            span.set_attribute("session.id", str(session.id))
            span.set_attribute("user.id", str(user.id))
            span.set_attribute("turn.number", 1)

            # Generate first question via LLM
            question_data = await self._generate_question(
                resume_text=resume_text,
                jd_text=jd_text,
                config=config,
                history=[],
                session_id=str(session.id),
            )

            # Store the interviewer turn
            turn = Turn(
                session_id=session.id,
                turn_number=1,
                role="interviewer",
                content=question_data["question"],
                topic=question_data.get("topic", "general"),
                difficulty=question_data.get("difficulty", 2),
                latency_ms=0,
            )
            db.add(turn)
            session.turn_count = 1
            await db.flush()

            SESSIONS_CREATED_TOTAL.inc()
            TURNS_PER_SESSION.observe(1)

            question_resp = QuestionResponse(
                turn_number=1,
                content=question_data["question"],
                topic=question_data.get("topic", "general"),
                difficulty=question_data.get("difficulty", 2),
            )
            return session, question_resp

    async def handle_response(
        self,
        db: AsyncSession,
        session: Session,
        candidate_content: str,
        resume_text: str = "",
        jd_text: str = "",
    ) -> QuestionResponse:
        """Process candidate answer and generate next question."""
        with tracer.start_as_current_span("orchestrator.handle_response") as span:
            if session.status != "active":
                raise ValueError("Session is not active")

            span.set_attribute("session.id", str(session.id))

            config = SessionConfig.model_validate(session.config or {})

            # Store candidate turn
            current_turn_number = session.turn_count + 1
            span.set_attribute("turn.number", current_turn_number)
            candidate_turn = Turn(
                session_id=session.id,
                turn_number=current_turn_number,
                role="candidate",
                content=candidate_content,
            )
            db.add(candidate_turn)
            session.turn_count = current_turn_number
            await db.flush()

            # Get conversation history
            stmt = select(Turn).where(Turn.session_id == session.id).order_by(Turn.turn_number)
            result = await db.execute(stmt)
            turns = list(result.scalars().all())

            history = [{"role": t.role, "content": t.content} for t in turns]

            # Generate next question
            question_data = await self._generate_question(
                resume_text=resume_text,
                jd_text=jd_text,
                config=config,
                history=history,
                session_id=str(session.id),
            )

            # Store interviewer turn
            next_turn_number = session.turn_count + 1
            interviewer_turn = Turn(
                session_id=session.id,
                turn_number=next_turn_number,
                role="interviewer",
                content=question_data["question"],
                topic=question_data.get("topic", "general"),
                difficulty=question_data.get("difficulty", 2),
            )
            db.add(interviewer_turn)
            session.turn_count = next_turn_number
            await db.flush()

            TURNS_PER_SESSION.observe(next_turn_number)

            # Collect covered topics
            topics_covered = list(
                set(t.topic for t in turns if t.topic and t.role == "interviewer")
            )
            if question_data.get("topic") and question_data["topic"] not in topics_covered:
                topics_covered.append(question_data["topic"])

            return QuestionResponse(
                turn_number=next_turn_number,
                content=question_data["question"],
                topic=question_data.get("topic", "general"),
                difficulty=question_data.get("difficulty", 2),
            )

    async def _generate_question(
        self,
        resume_text: str,
        jd_text: str,
        config: SessionConfig,
        history: list[dict],
        session_id: str,
    ) -> dict:
        """Call the LLM gateway to generate an interview question."""
        system_prompt = INTERVIEWER_SYSTEM_PROMPT.format(
            resume_text=resume_text or "Not provided",
            jd_text=jd_text or "Not provided",
            difficulty=config.difficulty,
            focus_topics=", ".join(config.focus_topics) if config.focus_topics else "any",
        )

        messages = [Message(role="system", content=system_prompt)]
        for entry in history:
            role = "user" if entry["role"] == "candidate" else "assistant"
            messages.append(Message(role=role, content=entry["content"]))

        if not history:
            messages.append(
                Message(
                    role="user", content="Please start the interview with your first question."
                )
            )
        else:
            messages.append(
                Message(role="user", content="Please ask the next interview question.")
            )

        result = await self._gateway.complete(
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            agent_type="interviewer",
            session_id=session_id,
            prompt_version="v1",
        )

        # Parse JSON response, with fallback
        try:
            data = json.loads(result.content)
            # Validate required fields
            if "question" not in data:
                raise ValueError("Missing 'question' field")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("llm_json_parse_failed", error=str(e), content_length=len(result.content))
            return {
                "question": result.content.strip(),
                "topic": "general",
                "difficulty": 2,
                "reasoning": "Fallback: could not parse structured response",
            }
