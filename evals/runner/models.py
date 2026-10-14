"""Data models and schemas for evaluation runs and golden sets."""

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator


class HumanScoreRange(BaseModel):
    """Min and max range for a human-labeled score."""

    min: float
    max: float

    @property
    def midpoint(self) -> float:
        """Calculate midpoint of the score range."""
        return (self.min + self.max) / 2.0


class GoldenCase(BaseModel):
    """A human-labeled test case in a golden set.

    Supports both flat format (role, question, answer, human_scores)
    and nested format (input: {...}, expected: {...}).
    """

    id: str = Field(default_factory=lambda: f"case-{uuid.uuid4().hex[:8]}")
    role: str = Field(default="", description="Target job role")
    question: str = Field(description="Interview question asked")
    answer: str = Field(description="Candidate's response to evaluate")
    human_scores: dict[str, float | int | dict[str, float | int]] = Field(
        description="Human gold standard scores per rubric dimension"
    )
    category: str = Field(default="general", description="Category: technical, behavioral, system-design, etc.")
    difficulty: int = Field(default=2, ge=1, le=5)
    jd_text: str = Field(default="", description="Job description context")
    rubric_dimensions: list[str] = Field(default_factory=list)
    evidence_must_reference: list[str] = Field(default_factory=list)
    is_injection: bool = Field(default=False, description="Whether answer contains prompt injection attempt")
    expected_answer_type: str = Field(default="attempted", description="attempted or no_answer")
    deprecated: bool = Field(default=False, description="Flagged as deprecated if updated")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input_expected(cls, data: Any) -> Any:
        """Allow loading from nested structures like input: {...}, expected: {...}."""
        if not isinstance(data, dict):
            return data

        # If nested format from eval_design.md
        if "input" in data and isinstance(data["input"], dict):
            inp = data["input"]
            exp = data.get("expected", {})

            data.setdefault("question", inp.get("question", ""))
            data.setdefault("answer", inp.get("answer", ""))
            data.setdefault("jd_text", inp.get("jd_text", ""))
            data.setdefault("role", inp.get("role", data.get("role", "")))
            data.setdefault("difficulty", inp.get("difficulty", data.get("difficulty", 2)))
            data.setdefault("category", data.get("category", inp.get("topic", "general")))

            if "rubric_dimensions" in inp and not data.get("rubric_dimensions"):
                data["rubric_dimensions"] = inp["rubric_dimensions"]

            if isinstance(exp, dict):
                if "scores" in exp and not data.get("human_scores"):
                    data["human_scores"] = exp["scores"]
                if "evidence_must_reference" in exp and not data.get("evidence_must_reference"):
                    data["evidence_must_reference"] = exp["evidence_must_reference"]
                if "answer_type" in exp and not data.get("expected_answer_type"):
                    data["expected_answer_type"] = exp["answer_type"]

        # If role is given but jd_text is empty, construct sensible default
        if data.get("role") and not data.get("jd_text"):
            data["jd_text"] = f"Target Role: {data['role']}"

        # If rubric_dimensions empty, derive from human_scores keys
        human_scores = data.get("human_scores")
        if isinstance(human_scores, dict) and not data.get("rubric_dimensions"):
            data["rubric_dimensions"] = list(human_scores.keys())

        return data

    def get_dimension_target(self, dimension: str) -> tuple[float, float, float]:
        """Return (min, max, target_midpoint) for a given dimension."""
        val = self.human_scores.get(dimension)
        if val is None:
            # Fallback if dimension wasn't directly in human_scores
            return (1.0, 5.0, 3.0)
        if isinstance(val, dict):
            mn = float(val.get("min", 1.0))
            mx = float(val.get("max", mn))
            return (mn, mx, (mn + mx) / 2.0)
        num_val = float(val)
        return (num_val, num_val, num_val)


class CaseRunResult(BaseModel):
    """Aggregate result for a single golden case scored over N repeats."""

    case_id: str
    role: str = ""
    question: str
    answer: str
    repeats: int
    dimension_scores: dict[str, list[int]] = Field(default_factory=dict)
    dimension_variances: dict[str, float] = Field(default_factory=dict)
    dimension_stds: dict[str, float] = Field(default_factory=dict)
    dimension_agreements: dict[str, float] = Field(default_factory=dict)
    dimension_maes: dict[str, float] = Field(default_factory=dict)
    evidence_validity_rates: dict[str, float] = Field(default_factory=dict)
    evidence_quotes: dict[str, list[str]] = Field(default_factory=dict)
    is_injection: bool = False
    injection_resisted: bool | None = None
    mean_latency_ms: float = 0.0
    cost_usd: float = 0.0
    is_unstable: bool = False


class EvalMetricsSummary(BaseModel):
    """Overall aggregated metrics for an evaluation run."""

    agreement_rate_within_one: float = Field(
        description="Fraction of scores within ±1 of human label"
    )
    mean_mae: float = Field(description="Mean Absolute Error across all scores")
    mean_run_variance: float = Field(description="Mean score variance across N repeats")
    mean_run_std: float = Field(description="Mean score standard deviation across N repeats")
    unstable_case_count: int = Field(description="Number of cases with high variance (std > 0.8)")
    evidence_validity_rate: float = Field(
        description="Fraction of evidence quotes that are valid substrings/citations"
    )
    injection_resistance_rate: float = Field(
        description="Pass rate of defending against prompt injection attacks"
    )
    cost_per_answer_usd: float = Field(description="Average LLM cost per answer evaluated")
    total_cost_usd: float = Field(description="Total LLM cost for entire run")
    total_tokens: int = Field(default=0, description="Total tokens used in run")
    latency_p50_ms: float = Field(description="Median latency in milliseconds")
    latency_p95_ms: float = Field(description="95th percentile latency in milliseconds")
    total_cases: int
    repeats: int


class EvalRunResult(BaseModel):
    """Complete results of an evaluation run."""

    run_id: str
    timestamp: str
    model_name: str
    prompt_version: str
    golden_set_path: str
    case_count: int
    repeats: int
    summary_metrics: EvalMetricsSummary
    case_results: list[CaseRunResult]
    passed_thresholds: bool = True
    threshold_failures: list[str] = Field(default_factory=list)
