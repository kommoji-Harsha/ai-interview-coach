"""Interviewer Agent: generates adaptive mock interview questions, follow-ups, and tracks topic coverage."""

from typing import Any

import structlog

from backend.agents.base import BaseAgent
from backend.agents.models import InterviewerInput, InterviewerResponse, TurnData
from backend.agents.prompt_loader import load_prompt_file, parse_prompt_sections, render_template
from backend.gateway.client import LLMGateway
from backend.gateway.models import Message

logger = structlog.get_logger()

TOPIC_UNIVERSE = [
    "behavioral",
    "technical",
    "system-design",
    "problem-solving",
    "culture-fit",
    "domain-specific",
]

CALIBRATION_QUESTION_BANK: dict[int, list[str]] = {
    1: [
        "Can you describe a software project you built and what technologies you chose?",
        "Tell me about a time you collaborated with a teammate on a project.",
    ],
    2: [
        "Walk me through a bug you encountered recently and how you diagnosed and resolved it.",
        "How do you approach writing automated tests to verify your implementation?",
    ],
    3: [
        "Describe a time when you had a technical disagreement with a colleague. How was it resolved?",
        "How would you design a RESTful API for an e-commerce shopping cart?",
    ],
    4: [
        "How would you design a distributed rate limiter that handles 100,000 requests per second across regions?",
        "Tell me about a situation where you had to make a difficult architectural trade-off under a tight deadline.",
    ],
    5: [
        "How would you architect a globally distributed event processing system ensuring strict ordering and exactly-once semantics?",
        "Describe how you drove an engineering-wide migration of a critical legacy platform with zero downtime.",
    ],
}


def infer_seniority_difficulty(jd_text: str) -> int:
    """Infer initial starting difficulty (1-5) from job description seniority keywords."""
    text = jd_text.lower()
    if any(keyword in text for keyword in ["staff", "principal", "director", "architect"]):
        return 5
    if any(keyword in text for keyword in ["senior", "sr.", "sr ", "lead"]):
        return 4
    if any(
        keyword in text
        for keyword in [
            "junior",
            "jr.",
            "jr ",
            "intern",
            "entry-level",
            "entry level",
            "associate",
        ]
    ):
        return 2
    return 3


def adapt_difficulty(current_difficulty: int, recent_scores: list[float]) -> int:
    """Adapt difficulty level based on recent performance scores.

    - avg >= 4.0 -> increase difficulty by 1 (max 5)
    - avg <= 2.0 -> decrease difficulty by 1 (min 1)
    - otherwise -> keep unchanged
    """
    if not recent_scores:
        return current_difficulty

    avg_score = sum(recent_scores) / len(recent_scores)
    if avg_score >= 4.0:
        return min(current_difficulty + 1, 5)
    elif avg_score <= 2.0:
        return max(current_difficulty - 1, 1)
    return current_difficulty


def select_next_topic(
    topics_covered: list[str],
    focus_topics: list[str] | None = None,
    scores_so_far: list[dict[str, Any]] | None = None,
) -> str:
    """Determine the next topic to ensure breadth or address user focus areas."""
    covered_set = set(t.strip().lower() for t in topics_covered)

    # 1. If focus topics are specified, prioritize uncovered focus topics
    if focus_topics:
        for topic in focus_topics:
            if topic.strip().lower() not in covered_set:
                return topic

    # 2. Pick uncovered topic from universe
    for topic in TOPIC_UNIVERSE:
        if topic not in covered_set:
            return topic

    # 3. If all topics are covered, check if there is a weakest topic from scores_so_far
    if scores_so_far:
        topic_scores: dict[str, list[float]] = {}
        for entry in scores_so_far:
            t = entry.get("topic")
            s = entry.get("score")
            if t and s is not None:
                topic_scores.setdefault(t, []).append(float(s))
        if topic_scores:
            weakest_topic = min(
                topic_scores.keys(),
                key=lambda t: sum(topic_scores[t]) / len(topic_scores[t]),
            )
            return weakest_topic

    # Default to first in universe
    return TOPIC_UNIVERSE[0]


class InterviewerAgent(BaseAgent[InterviewerInput, InterviewerResponse]):
    """Agent responsible for conducting the interview, adapting difficulty, and pacing topics."""

    agent_type = "interviewer"

    def __init__(
        self,
        gateway: LLMGateway,
        max_retries: int = 2,
        temperature: float = 0.7,
        version: str = "v1",
    ):
        super().__init__(
            gateway=gateway,
            response_model=InterviewerResponse,
            max_retries=max_retries,
            temperature=temperature,
            version=version,
        )
        raw_prompt = load_prompt_file(self.agent_type, version=self.version)
        self._system_template, self._user_template = parse_prompt_sections(raw_prompt)

    def format_history(self, history: list[TurnData]) -> str:
        """Format turn history cleanly for prompt context."""
        if not history:
            return "No previous conversation. This is the first turn."
        lines: list[str] = []
        for turn in history:
            role_label = "Interviewer" if turn.role == "interviewer" else "Candidate"
            lines.append(f"Turn {turn.turn_number} [{role_label}]: {turn.content}")
        return "\n".join(lines)

    def format_scores(self, scores: list[dict[str, Any]]) -> str:
        """Format past scores for prompt context."""
        if not scores:
            return "None yet."
        formatted = []
        for s in scores:
            dim = s.get("dimension", "overall")
            val = s.get("score", "N/A")
            formatted.append(f"{dim}: {val}")
        return ", ".join(formatted)

    def build_prompt(self, input_data: InterviewerInput) -> list[Message]:
        """Construct isolated System and User messages with prompt template."""
        # Calibration questions for this difficulty
        calibration_qs = CALIBRATION_QUESTION_BANK.get(
            input_data.difficulty_level, CALIBRATION_QUESTION_BANK[3]
        )
        sample_str = "\n".join(f"- {q}" for q in calibration_qs)

        system_vars = {
            "topics_covered": ", ".join(input_data.topics_covered)
            if input_data.topics_covered
            else "None",
            "focus_topics": ", ".join(input_data.focus_topics)
            if input_data.focus_topics
            else "Any relevant topic",
            "difficulty_level": input_data.difficulty_level,
            "turn_number": input_data.turn_number,
            "max_turns": input_data.max_turns,
            "question_bank_sample": sample_str,
        }
        system_content = render_template(self._system_template, system_vars)

        user_vars = {
            "resume_text": input_data.resume_text.strip() or "Not provided",
            "jd_text": input_data.jd_text.strip() or "Not provided",
            "conversation_history": self.format_history(input_data.conversation_history),
            "scores_so_far": self.format_scores(input_data.scores_so_far),
        }
        user_content = render_template(self._user_template, user_vars)

        return [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

    def handle_fallback(
        self,
        input_data: InterviewerInput,
        last_error: Exception,
        last_raw: str | None,
    ) -> InterviewerResponse:
        """Fallback to question bank calibration when generation fails."""
        logger.warning(
            "interviewer_fallback_to_question_bank",
            error=str(last_error),
            difficulty=input_data.difficulty_level,
        )
        candidates = CALIBRATION_QUESTION_BANK.get(
            input_data.difficulty_level, CALIBRATION_QUESTION_BANK[3]
        )
        fallback_question = candidates[0]
        suggested_topic = select_next_topic(
            input_data.topics_covered, input_data.focus_topics, input_data.scores_so_far
        )
        return InterviewerResponse(
            question=fallback_question,
            topic=suggested_topic,
            subtopic="calibration",
            difficulty=input_data.difficulty_level,
            reasoning="Fallback: calibrated question from question bank after LLM generation failure.",
            is_follow_up=False,
            source="question_bank",
        )
