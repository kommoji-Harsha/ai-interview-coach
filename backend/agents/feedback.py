"""Feedback Agent: generates end-of-session performance summary, improvement plan, and readiness assessment."""

import structlog

from backend.agents.base import BaseAgent
from backend.agents.models import FeedbackInput, FeedbackResponse, TurnData, TurnScores
from backend.agents.prompt_loader import load_prompt_file, parse_prompt_sections, render_template
from backend.gateway.client import LLMGateway
from backend.gateway.models import Message

logger = structlog.get_logger()


def generate_template_feedback(
    aggregate_scores: dict[str, float],
    turns: list[TurnData],
) -> FeedbackResponse:
    """Generate deterministic, template-based feedback when LLM generation is unavailable or fails."""
    # Compute overall average if not present
    scores_list = [
        v for k, v in aggregate_scores.items() if k != "overall" and isinstance(v, (int, float))
    ]
    overall = aggregate_scores.get("overall") or (
        sum(scores_list) / len(scores_list) if scores_list else 3.0
    )

    if overall >= 4.0:
        readiness = "interview_ready"
        summary_intro = "Great performance across the interview. You demonstrated clear communication and strong technical foundations."
    elif overall >= 2.8:
        readiness = "progressing"
        summary_intro = "Solid baseline performance with clear opportunities to deepen technical specifics and structure answers."
    else:
        readiness = "needs_work"
        summary_intro = "Foundational interview practice needed. Focus on structuring responses and adding concrete technical evidence."

    strengths: list[str] = []
    improvements: list[str] = []
    recommended_topics: list[str] = []
    action_items: list[str] = []

    # Categorize by scores
    for dim, score in aggregate_scores.items():
        if dim == "overall":
            continue
        if score >= 3.5:
            strengths.append(
                f"Strong performance in {dim.replace('_', ' ')} (score: {score:.1f}/5.0)"
            )
        else:
            improvements.append(
                f"Develop greater depth in {dim.replace('_', ' ')} (score: {score:.1f}/5.0)"
            )
            recommended_topics.append(dim.replace("_", "-"))

    if not strengths:
        strengths = ["Willingness to attempt diverse technical and behavioral questions"]
    if not improvements:
        improvements = ["Continue refining conciseness and pacing during complex explanations"]
        recommended_topics = ["system-design", "behavioral"]

    for dim in recommended_topics[:3]:
        action_items.append(f"Practice timed mock sessions focusing specifically on {dim}")

    if not action_items:
        action_items = [
            "Review core architectural trade-offs under timed conditions",
            "Prepare 3 concrete STAR-format stories highlighting quantifiable results",
        ]

    summary = f"{summary_intro} Completed {len(turns)} conversation turns with an overall score of {overall:.1f}/5.0."
    if len(summary) > 500:
        summary = summary[:497] + "..."

    return FeedbackResponse(
        summary=summary,
        strengths=strengths[:5],
        improvements=improvements[:5],
        action_items=action_items[:5],
        recommended_topics=recommended_topics[:4] or ["general"],
        estimated_readiness=readiness,
        feedback_source="template",
    )


class FeedbackAgent(BaseAgent[FeedbackInput, FeedbackResponse]):
    """Agent that synthesizes full interview history and scores into coaching feedback."""

    agent_type = "feedback"

    def __init__(
        self,
        gateway: LLMGateway,
        max_retries: int = 2,
        temperature: float = 0.4,
        version: str = "v1",
    ):
        super().__init__(
            gateway=gateway,
            response_model=FeedbackResponse,
            max_retries=max_retries,
            temperature=temperature,
            version=version,
        )
        raw_prompt = load_prompt_file(self.agent_type, version=self.version)
        self._system_template, self._user_template = parse_prompt_sections(raw_prompt)

    def format_conversation(self, turns: list[TurnData], scores: list[TurnScores]) -> str:
        """Format turn history with associated scores for the prompt."""
        scores_by_turn: dict[int, list[str]] = {}
        for ts in scores:
            scores_by_turn[ts.turn_number] = [
                f"{s.dimension}: {s.score}/5 (evidence: '{s.evidence}')" for s in ts.scores
            ]

        formatted_lines: list[str] = []
        for t in turns:
            role_label = "Interviewer" if t.role == "interviewer" else "Candidate"
            line = f"Turn {t.turn_number} [{role_label}]: {t.content}"
            if t.turn_number in scores_by_turn:
                line += f"\n  Scores: {', '.join(scores_by_turn[t.turn_number])}"
            formatted_lines.append(line)

        return "\n".join(formatted_lines) if formatted_lines else "No conversation recorded."

    def build_prompt(self, input_data: FeedbackInput) -> list[Message]:
        """Construct prompt with isolated resume, JD, and interview history."""
        system_content = render_template(self._system_template, {})

        formatted_conv = self.format_conversation(input_data.turns, input_data.scores)
        agg_str = ", ".join(f"{k}: {v:.1f}" for k, v in input_data.aggregate_scores.items())

        user_vars = {
            "resume_text": input_data.resume_text.strip() or "Not provided",
            "jd_text": input_data.jd_text.strip() or "Not provided",
            "conversation": formatted_conv,
            "aggregate_scores": agg_str or "None calculated",
        }
        user_content = render_template(self._user_template, user_vars)

        return [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

    def handle_fallback(
        self,
        input_data: FeedbackInput,
        last_error: Exception,
        last_raw: str | None,
    ) -> FeedbackResponse:
        """Fallback to deterministic template feedback when LLM generation fails repeatedly."""
        logger.warning(
            "feedback_fallback_to_template",
            error=str(last_error),
        )
        return generate_template_feedback(
            aggregate_scores=input_data.aggregate_scores,
            turns=input_data.turns,
        )
