"""Scorer Agent: evaluates candidate answers on rubric dimensions with evidence quotes, confidence, and retry handling."""

import re

import structlog

from backend.agents.base import BaseAgent
from backend.agents.models import DimensionScore, ScoreResponse, ScorerInput
from backend.agents.prompt_loader import load_prompt_file, parse_prompt_sections, render_template
from backend.gateway.client import LLMGateway
from backend.gateway.models import Message
from backend.observability.metrics import SCORE_VALUE, SCORES_GENERATED_TOTAL
from backend.observability.tracing import get_tracer

logger = structlog.get_logger()
tracer = get_tracer("ai-interview-coach.scorer")

# Standard rubric dimensions by topic
DEFAULT_RUBRIC_BY_TOPIC: dict[str, list[str]] = {
    "behavioral": ["communication", "relevance", "examples"],
    "culture-fit": ["communication", "relevance", "examples"],
    "technical": ["relevance", "technical_depth", "problem_solving"],
    "problem-solving": ["relevance", "technical_depth", "problem_solving"],
    "system-design": [
        "communication",
        "relevance",
        "technical_depth",
        "problem_solving",
        "examples",
    ],
}

FALLBACK_RUBRIC = ["communication", "relevance", "technical_depth"]

NO_ANSWER_PATTERNS = [
    r"\b(i\s+don'?t\s+know|idk|no\s+idea|skip|pass|no\s+answer)\b",
    r"\b(can\s+we\s+skip|i\s+have\s+no\s+experience\s+with\s+this)\b",
]


def resolve_rubric_dimensions(
    topic: str, requested_dimensions: list[str] | None = None
) -> list[str]:
    """Determine rubric dimensions to evaluate based on topic or explicit list."""
    if requested_dimensions:
        return requested_dimensions
    topic_key = topic.lower().strip()
    return DEFAULT_RUBRIC_BY_TOPIC.get(topic_key, FALLBACK_RUBRIC)


def is_obvious_no_answer(answer: str) -> bool:
    """Check if candidate text is empty or an obvious short pass/skip."""
    text = answer.strip().lower()
    if not text or len(text) < 3:
        return True
    if len(text) < 80:
        return any(bool(re.search(pattern, text)) for pattern in NO_ANSWER_PATTERNS)
    return False


class ScorerAgent(BaseAgent[ScorerInput, ScoreResponse]):
    """Agent that scores a single candidate answer against a multi-dimensional rubric."""

    agent_type = "scorer"

    def __init__(
        self,
        gateway: LLMGateway,
        max_retries: int = 2,
        temperature: float = 0.2,
        version: str = "v1",
    ):
        super().__init__(
            gateway=gateway,
            response_model=ScoreResponse,
            max_retries=max_retries,
            temperature=temperature,
            version=version,
        )
        raw_prompt = load_prompt_file(self.agent_type, version=self.version)
        self._system_template, self._user_template = parse_prompt_sections(raw_prompt)

    def build_prompt(self, input_data: ScorerInput) -> list[Message]:
        """Construct prompt for scoring, isolating user answer in XML tags."""
        dimensions = resolve_rubric_dimensions(input_data.topic, input_data.rubric_dimensions)
        dim_str = ", ".join(dimensions)

        system_content = render_template(self._system_template, {})

        user_vars = {
            "question": input_data.question.strip(),
            "answer": input_data.answer.strip() or "No response provided",
            "jd_text": input_data.jd_text.strip() or "Not provided",
            "topic": input_data.topic,
            "difficulty": input_data.difficulty,
            "rubric_dimensions": dim_str,
        }
        user_content = render_template(self._user_template, user_vars)

        return [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

    def validate_and_postprocess(
        self, raw_content: str, requested_dimensions: list[str]
    ) -> ScoreResponse:
        """Validate JSON against ScoreResponse schema and verify requested dimensions."""
        parsed = self.validate(raw_content)

        # Check dimension completeness
        scored_dims = {s.dimension.lower().strip() for s in parsed.scores}
        missing = [d for d in requested_dimensions if d.lower().strip() not in scored_dims]
        if missing:
            raise ValueError(
                f"Missing required rubric dimension(s) in evaluation: {missing}. "
                f"Scored dimensions were: {list(scored_dims)}"
            )

        # Flag low-confidence scores for human review
        for dim_score in parsed.scores:
            if dim_score.confidence < 0.6:
                dim_score.needs_review = True

        return parsed

    async def run(
        self,
        input_data: ScorerInput,
        session_id: str | None = None,
        model: str | None = None,
    ) -> ScoreResponse:
        """Run scoring with fast path for obvious skips and retry validation for LLM calls."""
        effective_dimensions = resolve_rubric_dimensions(
            input_data.topic, input_data.rubric_dimensions
        )

        # Fast path for explicit empty or refusal answers
        if is_obvious_no_answer(input_data.answer):
            return ScoreResponse(
                answer_type="no_answer",
                scores=[
                    DimensionScore(
                        dimension=dim,
                        score=1,
                        evidence="Not addressed (candidate skipped or gave no answer)",
                        confidence=1.0,
                        needs_review=False,
                    )
                    for dim in effective_dimensions
                ],
                overall_impression="The candidate did not attempt or skipped this question.",
            )

        messages = self.build_prompt(input_data)
        history = list(messages)
        last_raw: str | None = None
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._gateway.complete(
                    messages=history,
                    model=model,
                    temperature=self.temperature,
                    agent_type=self.agent_type,
                    session_id=session_id,
                    prompt_version=self.version,
                )
                last_raw = result.content
                parsed = self.validate_and_postprocess(result.content, effective_dimensions)
                for s in parsed.scores:
                    SCORES_GENERATED_TOTAL.labels(dimension=s.dimension).inc()
                    SCORE_VALUE.labels(dimension=s.dimension).observe(s.score)
                return parsed

            except Exception as err:
                last_error = err
                logger.warning(
                    "scorer_validation_failed",
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    error=str(err),
                )
                if attempt < self.max_retries:
                    raw_str = str(last_raw) if last_raw is not None else ""
                    history.append(Message(role="assistant", content=raw_str))
                    history.append(
                        Message(
                            role="user",
                            content=(
                                f"Your response was invalid: {err}. Ensure all requested dimensions "
                                f"({effective_dimensions}) are scored and output ONLY valid JSON."
                            ),
                        )
                    )

        # Fallback if LLM consistently fails to output valid schema
        logger.error("scorer_all_retries_failed_using_fallback", error=str(last_error))
        return ScoreResponse(
            answer_type="attempted",
            scores=[
                DimensionScore(
                    dimension=dim,
                    score=3,
                    evidence="Evaluation fallback: default median score assigned due to parsing error.",
                    confidence=0.5,
                    needs_review=True,
                )
                for dim in effective_dimensions
            ],
            overall_impression="Could not complete automated scoring; flagged for manual review.",
        )
