"""Tests for evaluation threshold gating and regression checks."""

from evals.runner.check_thresholds import verify_thresholds
from evals.runner.config import EvalConfig
from evals.runner.models import EvalMetricsSummary


def _create_summary(
    agreement: float = 0.85,
    mae: float = 0.70,
    std: float = 0.35,
    evidence: float = 0.90,
    injection: float = 1.0,
    cost_per_answer: float = 0.002,
) -> EvalMetricsSummary:
    return EvalMetricsSummary(
        agreement_rate_within_one=agreement,
        mean_mae=mae,
        mean_run_variance=std**2,
        mean_run_std=std,
        unstable_case_count=0,
        evidence_validity_rate=evidence,
        injection_resistance_rate=injection,
        cost_per_answer_usd=cost_per_answer,
        total_cost_usd=cost_per_answer * 10,
        total_tokens=1000,
        latency_p50_ms=200.0,
        latency_p95_ms=450.0,
        total_cases=10,
        repeats=3,
    )


def test_verify_thresholds_all_passed():
    summary = _create_summary()
    config = EvalConfig(agreement_threshold=0.80)
    passed, failures = verify_thresholds(summary, config)
    assert passed is True
    assert len(failures) == 0


def test_verify_thresholds_agreement_failed():
    summary = _create_summary(agreement=0.72)
    config = EvalConfig(agreement_threshold=0.80)
    passed, failures = verify_thresholds(summary, config)
    assert passed is False
    assert any("Agreement rate within ±1" in f for f in failures)


def test_verify_thresholds_mae_and_std_failed():
    summary = _create_summary(mae=1.4, std=0.65)
    config = EvalConfig(max_mae=1.0, max_run_std=0.5)
    passed, failures = verify_thresholds(summary, config)
    assert passed is False
    assert any("Mean Absolute Error" in f for f in failures)
    assert any("standard deviation" in f for f in failures)


def test_verify_thresholds_injection_failed():
    summary = _create_summary(injection=0.80)
    config = EvalConfig(injection_resistance_threshold=1.0)
    passed, failures = verify_thresholds(summary, config)
    assert passed is False
    assert any("Prompt injection resistance" in f for f in failures)


def test_verify_thresholds_regression_detection():
    baseline = _create_summary(agreement=0.90)
    # 0.78 is > 10% drop from 0.90 (0.90 * 0.90 = 0.81 minimum allowed)
    current = _create_summary(agreement=0.78)
    config = EvalConfig(agreement_threshold=0.70, regression_tolerance=0.10)

    passed, failures = verify_thresholds(
        current, config=config, baseline_metrics=baseline
    )
    assert passed is False
    assert any("Regression detected" in f for f in failures)
