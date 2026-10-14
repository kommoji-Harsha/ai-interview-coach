"""Aggregation module to synthesize case-level metrics into run summaries."""

from evals.metrics.agreement import compute_agreement_rate
from evals.metrics.cost import compute_cost_metrics
from evals.metrics.injection import compute_injection_pass_rate
from evals.metrics.variance import compute_score_std
from evals.runner.models import CaseRunResult, EvalMetricsSummary


def aggregate_metrics(
    case_results: list[CaseRunResult],
    execution_records: list[dict],
    repeats: int,
) -> EvalMetricsSummary:
    """Compute overall run metrics by aggregating case run results and performance logs.

    Args:
        case_results: List of CaseRunResult objects evaluated across repeats.
        execution_records: Low-level logs of each LLM call (latency, tokens, cost).
        repeats: Number of repeat runs per case.

    Returns:
        Consolidated EvalMetricsSummary instance.
    """
    total_cases = len(case_results)
    if total_cases == 0:
        return EvalMetricsSummary(
            agreement_rate_within_one=1.0,
            mean_mae=0.0,
            mean_run_variance=0.0,
            mean_run_std=0.0,
            unstable_case_count=0,
            evidence_validity_rate=1.0,
            injection_resistance_rate=1.0,
            cost_per_answer_usd=0.0,
            total_cost_usd=0.0,
            total_tokens=0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            total_cases=0,
            repeats=repeats,
        )

    all_agreements: list[float] = []
    all_maes: list[float] = []
    all_variances: list[float] = []
    all_stds: list[float] = []
    all_evidence_rates: list[float] = []
    injection_outcomes: list[tuple[bool, str]] = []
    unstable_count = 0

    for case in case_results:
        if case.is_unstable:
            unstable_count += 1

        for agr in case.dimension_agreements.values():
            all_agreements.append(agr)
        for mae in case.dimension_maes.values():
            all_maes.append(mae)
        for var in case.dimension_variances.values():
            all_variances.append(var)
        for std in case.dimension_stds.values():
            all_stds.append(std)
        for ev_rate in case.evidence_validity_rates.values():
            all_evidence_rates.append(ev_rate)

        if case.is_injection and case.injection_resisted is not None:
            injection_outcomes.append((case.injection_resisted, case.case_id))

    mean_agreement = (
        sum(all_agreements) / len(all_agreements) if all_agreements else 1.0
    )
    mean_mae = sum(all_maes) / len(all_maes) if all_maes else 0.0
    mean_variance = sum(all_variances) / len(all_variances) if all_variances else 0.0
    mean_std = sum(all_stds) / len(all_stds) if all_stds else 0.0
    evidence_rate = (
        sum(all_evidence_rates) / len(all_evidence_rates) if all_evidence_rates else 1.0
    )
    injection_rate = compute_injection_pass_rate(injection_outcomes)

    cost_info = compute_cost_metrics(execution_records, total_answers=total_cases)

    return EvalMetricsSummary(
        agreement_rate_within_one=round(mean_agreement, 4),
        mean_mae=round(mean_mae, 4),
        mean_run_variance=round(mean_variance, 4),
        mean_run_std=round(mean_std, 4),
        unstable_case_count=unstable_count,
        evidence_validity_rate=round(evidence_rate, 4),
        injection_resistance_rate=round(injection_rate, 4),
        cost_per_answer_usd=float(cost_info["cost_per_answer_usd"]),
        total_cost_usd=float(cost_info["total_cost_usd"]),
        total_tokens=int(cost_info["total_tokens"]),
        latency_p50_ms=float(cost_info["latency_p50_ms"]),
        latency_p95_ms=float(cost_info["latency_p95_ms"]),
        total_cases=total_cases,
        repeats=repeats,
    )
