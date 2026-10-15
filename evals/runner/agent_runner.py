"""Scorer agent execution harness for running cases N times with metric tracking."""

import json
import time
from typing import Any

from backend.agents.models import ScorerInput
from backend.agents.scorer import ScorerAgent
from backend.gateway.models import LLMResult, Message
from evals.metrics.agreement import compute_agreement_within_one, compute_mae
from evals.metrics.cost import estimate_token_cost
from evals.metrics.evidence import compute_evidence_validity
from evals.metrics.injection import evaluate_injection_resistance
from evals.metrics.variance import (
    compute_run_variance,
    compute_score_std,
    is_case_unstable,
)
from evals.runner.models import CaseRunResult, GoldenCase


class MockEvaluationGateway:
    """Mock LLM Gateway for deterministic offline evaluation and testing without API calls."""

    async def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.2,
        agent_type: str = "scorer",
        session_id: str | None = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Generate deterministic score response based on prompt contents."""
        user_msg = next((m.content for m in messages if m.role == "user"), "")

        # Extract answer and dimensions from user message
        answer = ""
        if "<answer>" in user_msg and "</answer>" in user_msg:
            answer = user_msg.split("<answer>")[1].split("</answer>")[0].strip()

        dim_line = ""
        for line in user_msg.splitlines():
            if "Dimensions to score:" in line:
                dim_line = line.split("Dimensions to score:")[1].strip()

        dimensions = [d.strip() for d in dim_line.split(",") if d.strip()] or [
            "communication",
            "relevance",
            "technical_depth",
        ]

        technical_keywords = [
            "redis",
            "b-tree",
            "database",
            "postgres",
            "sql",
            "nosql",
            "migration",
            "team of five",
            "distributed",
            "event bubbling",
            "dom",
            "tcp",
            "syn",
            "connection pooling",
            "batch",
            "stream",
            "kafka",
            "rdb",
            "aof",
            "idempotent",
            "bloom",
        ]
        is_substantive = (
            any(kw in answer.lower() for kw in technical_keywords) or len(answer) > 120
        )

        # Handle Prompt Injection Attempts
        if "SYSTEM OVERRIDE" in answer or "prompt injection" in answer.lower():
            scores = [
                {
                    "dimension": dim,
                    "score": 1,
                    "evidence": "SYSTEM OVERRIDE (attempted prompt injection detected)",
                    "confidence": 0.95,
                }
                for dim in dimensions
            ]
            content = json.dumps(
                {
                    "answer_type": "no_answer",
                    "scores": scores,
                    "overall_impression": "Candidate attempted a system prompt injection attack; refusal score assigned.",
                }
            )
        elif "don't know" in answer.lower() or "never used one" in answer.lower():
            scores = [
                {
                    "dimension": dim,
                    "score": 1,
                    "evidence": "Candidate explicitly stated: 'I don't know actually. I've never used one.'",
                    "confidence": 1.0,
                }
                for dim in dimensions
            ]
            content = json.dumps(
                {
                    "answer_type": "no_answer",
                    "scores": scores,
                    "overall_impression": "Candidate skipped the question.",
                }
            )
        elif is_substantive:
            # High quality detailed answer
            first_clause = answer.split(".")[0].strip()
            scores = [
                {
                    "dimension": dim,
                    "score": 5 if dim in ["communication", "relevance"] else 4,
                    "evidence": f"Candidate stated: '{first_clause}'",
                    "confidence": 0.90,
                }
                for dim in dimensions
            ]
            content = json.dumps(
                {
                    "answer_type": "attempted",
                    "scores": scores,
                    "overall_impression": "Strong comprehensive response with concrete domain specifics.",
                }
            )
        else:
            # Brief / weak answer
            scores = [
                {
                    "dimension": dim,
                    "score": 2,
                    "evidence": f"Brief response provided: '{answer[:40]}'",
                    "confidence": 0.70,
                }
                for dim in dimensions
            ]
            content = json.dumps(
                {
                    "answer_type": "attempted",
                    "scores": scores,
                    "overall_impression": "Answer addressed the topic at a superficial level.",
                }
            )

        prompt_tokens = len(user_msg.split()) * 2
        completion_tokens = len(content.split()) * 2

        return LLMResult(
            content=content,
            model=model or "mock-scorer-llm",
            provider="mock",
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=120,
            cached=False,
        )


async def score_case_n_times(
    agent: ScorerAgent,
    case: GoldenCase,
    repeats: int = 3,
    model: str | None = None,
) -> tuple[CaseRunResult, list[dict[str, Any]]]:
    """Score a single GoldenCase N times using the provided ScorerAgent.

    Tracks score distributions, variances, evidence quotes, latency, and costs.

    Args:
        agent: Initialized ScorerAgent.
        case: GoldenCase to evaluate.
        repeats: Number of times to score this answer.
        model: Optional model identifier override.

    Returns:
        (case_result, execution_records)
    """
    dimension_scores: dict[str, list[int]] = {dim: [] for dim in case.rubric_dimensions}
    evidence_quotes: dict[str, list[str]] = {dim: [] for dim in case.rubric_dimensions}
    latencies: list[float] = []
    case_total_cost = 0.0
    execution_records: list[dict[str, Any]] = []

    last_answer_type = case.expected_answer_type
    last_predicted_map: dict[str, int] = {}

    for _ in range(repeats):
        scorer_input = ScorerInput(
            question=case.question,
            answer=case.answer,
            topic=case.category,
            difficulty=case.difficulty,
            jd_text=case.jd_text,
            rubric_dimensions=case.rubric_dimensions,
        )

        start_time = time.perf_counter()
        response = await agent.run(scorer_input, model=model)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latencies.append(elapsed_ms)

        last_answer_type = response.answer_type

        # Extract tokens and cost estimates
        prompt_words = len(case.question) + len(case.answer) + len(case.jd_text)
        prompt_tokens = max(int(prompt_words / 3.5), 150)
        completion_tokens = 200
        cost_usd = estimate_token_cost(prompt_tokens, completion_tokens)
        case_total_cost += cost_usd

        execution_records.append(
            {
                "case_id": case.id,
                "latency_ms": elapsed_ms,
                "cost_usd": cost_usd,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )

        # Record scores and evidence per dimension
        current_repeat_scores: dict[str, int] = {}
        for dim_score in response.scores:
            dim_name = dim_score.dimension
            if dim_name not in dimension_scores:
                dimension_scores[dim_name] = []
                evidence_quotes[dim_name] = []
            dimension_scores[dim_name].append(dim_score.score)
            evidence_quotes[dim_name].append(dim_score.evidence)
            current_repeat_scores[dim_name] = dim_score.score

        last_predicted_map = current_repeat_scores

    # Compute per-dimension metrics across N repeats
    dimension_variances: dict[str, float] = {}
    dimension_stds: dict[str, float] = {}
    dimension_agreements: dict[str, float] = {}
    dimension_maes: dict[str, float] = {}
    evidence_validity_rates: dict[str, float] = {}

    for dim, scores in dimension_scores.items():
        dimension_variances[dim] = round(compute_run_variance(scores), 4)
        dimension_stds[dim] = round(compute_score_std(scores), 4)

        target_min, target_max, _midpoint = case.get_dimension_target(dim)
        target_dict = {"min": target_min, "max": target_max}

        agreements = [
            1.0 if compute_agreement_within_one(s, target_dict) else 0.0 for s in scores
        ]
        dimension_agreements[dim] = round(sum(agreements) / max(len(agreements), 1), 4)

        maes = [compute_mae(s, target_dict) for s in scores]
        dimension_maes[dim] = round(sum(maes) / max(len(maes), 1), 4)

        quotes = evidence_quotes.get(dim, [])
        evidence_validity_rates[dim] = round(
            compute_evidence_validity(
                quotes,
                case.answer,
                answer_type=last_answer_type,
                required_phrases=case.evidence_must_reference,
            ),
            4,
        )

    # Injection resistance evaluation
    injection_resisted: bool | None = None
    if case.is_injection:
        resisted, _ = evaluate_injection_resistance(
            case,
            last_predicted_map,
            answer_type=last_answer_type,
        )
        injection_resisted = resisted

    unstable = is_case_unstable(dimension_scores)

    case_result = CaseRunResult(
        case_id=case.id,
        role=case.role,
        question=case.question,
        answer=case.answer,
        repeats=repeats,
        dimension_scores=dimension_scores,
        dimension_variances=dimension_variances,
        dimension_stds=dimension_stds,
        dimension_agreements=dimension_agreements,
        dimension_maes=dimension_maes,
        evidence_validity_rates=evidence_validity_rates,
        evidence_quotes=evidence_quotes,
        is_injection=case.is_injection,
        injection_resisted=injection_resisted,
        mean_latency_ms=round(sum(latencies) / max(len(latencies), 1), 2),
        cost_usd=round(case_total_cost, 6),
        is_unstable=unstable,
    )

    return case_result, execution_records
