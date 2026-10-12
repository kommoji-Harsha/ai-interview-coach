"""Pydantic schemas and data models for AI Interview Coach agents."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TurnData(BaseModel):
    """Represents a single turn in the interview conversation history."""

    turn_number: int
    role: str  # "interviewer" | "candidate"
    content: str
    topic: str | None = None
    difficulty: int | None = None


# ---------------------------------------------------------------------------
# Interviewer Agent Models
# ---------------------------------------------------------------------------


class InterviewerInput(BaseModel):
    """Input payload for the Interviewer Agent."""

    resume_text: str = ""
    jd_text: str = ""
    conversation_history: list[TurnData] = Field(default_factory=list)
    topics_covered: list[str] = Field(default_factory=list)
    scores_so_far: list[dict[str, Any]] = Field(default_factory=list)
    difficulty_level: int = Field(default=2, ge=1, le=5)
    turn_number: int = Field(default=1, ge=1)
    max_turns: int = Field(default=10, ge=1)
    question_bank_sample: list[str] = Field(default_factory=list)
    focus_topics: list[str] | None = None


class InterviewerResponse(BaseModel):
    """Structured response from the Interviewer Agent."""

    question: str = Field(min_length=10, description="The interview question")
    topic: str = Field(description="Category (behavioral, technical, system-design, etc.)")
    subtopic: str = Field(default="", description="Specific skill or domain area")
    difficulty: int = Field(ge=1, le=5, description="Calibrated difficulty 1 to 5")
    reasoning: str = Field(description="Why this question was selected")
    is_follow_up: bool = Field(default=False, description="Whether this probes a prior answer")
    source: str = Field(default="llm", description="Origin: llm or question_bank")


# ---------------------------------------------------------------------------
# Scorer Agent Models
# ---------------------------------------------------------------------------


class ScorerInput(BaseModel):
    """Input payload for scoring a candidate answer."""

    question: str
    answer: str
    topic: str = "general"
    difficulty: int = 2
    jd_text: str = ""
    rubric_dimensions: list[str] = Field(default_factory=list)


class DimensionScore(BaseModel):
    """Evaluation score for a single rubric dimension."""

    dimension: str
    score: int = Field(ge=1, le=5, description="Rubric score from 1 (poor) to 5 (excellent)")
    evidence: str = Field(description="Direct quote or paraphrase from answer, or 'Not addressed'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    needs_review: bool = Field(default=False, description="Flagged for low confidence (< 0.6)")


class ScoreResponse(BaseModel):
    """Structured output from the Scorer Agent."""

    answer_type: Literal["attempted", "no_answer"]
    scores: list[DimensionScore] = Field(min_length=1)
    overall_impression: str = Field(description="1-2 sentence impression or hint")

    @model_validator(mode="after")
    def validate_answer_type_scores(self) -> "ScoreResponse":
        """If answer_type is no_answer, all scores should reflect unaddressed state."""
        if self.answer_type == "no_answer":
            for s in self.scores:
                if s.evidence.strip() == "":
                    s.evidence = "Not addressed"
        return self


# ---------------------------------------------------------------------------
# Feedback Agent Models
# ---------------------------------------------------------------------------


class TurnScores(BaseModel):
    """Scores associated with a turn."""

    turn_number: int
    scores: list[DimensionScore] = Field(default_factory=list)


class FeedbackInput(BaseModel):
    """Input payload for generating end-of-session feedback."""

    turns: list[TurnData] = Field(default_factory=list)
    scores: list[TurnScores] = Field(default_factory=list)
    resume_text: str = ""
    jd_text: str = ""
    aggregate_scores: dict[str, float] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    """Structured end-of-session feedback and improvement plan."""

    summary: str = Field(max_length=500, description="Session summary (max 500 characters)")
    strengths: list[str] = Field(min_length=1, max_length=5, description="Observed strengths")
    improvements: list[str] = Field(min_length=1, max_length=5, description="Areas for growth")
    action_items: list[str] = Field(min_length=1, max_length=5, description="Concrete next steps")
    recommended_topics: list[str] = Field(
        default_factory=list, description="Recommended topics to practice"
    )
    estimated_readiness: Literal["needs_work", "progressing", "interview_ready"]
    feedback_source: str = Field(default="llm", description="Origin: llm or template")

    @field_validator("summary", mode="before")
    @classmethod
    def trim_summary(cls, v: Any) -> Any:
        """Trim summary to 500 characters if slightly over, preserving valid output."""
        if isinstance(v, str) and len(v) > 500:
            return v[:497] + "..."
        return v

    @model_validator(mode="after")
    def validate_strengths_and_improvements(self) -> "FeedbackResponse":
        """Ensure no exact duplicate items between strengths and improvements."""
        strength_set = {s.strip().lower() for s in self.strengths}
        improvement_set = {i.strip().lower() for i in self.improvements}
        overlap = strength_set & improvement_set
        if overlap:
            raise ValueError(
                f"Strengths and improvements must not overlap on items: {sorted(overlap)}"
            )
        return self
