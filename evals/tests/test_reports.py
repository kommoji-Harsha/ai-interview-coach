"""Tests for report generation (JSON, Markdown) and history tracking."""

from evals.reports.generator import (
    generate_json_report,
    generate_markdown_report,
)
from evals.reports.history import (
    append_run_history,
    get_latest_baseline,
    load_run_history,
)
from evals.runner.models import (
    CaseRunResult,
    EvalMetricsSummary,
    EvalRunResult,
)


def _build_sample_eval_result() -> EvalRunResult:
    summary = EvalMetricsSummary(
        agreement_rate_within_one=0.88,
        mean_mae=0.65,
        mean_run_variance=0.12,
        mean_run_std=0.34,
        unstable_case_count=0,
        evidence_validity_rate=0.92,
        injection_resistance_rate=1.0,
        cost_per_answer_usd=0.0012,
        total_cost_usd=0.012,
        total_tokens=1500,
        latency_p50_ms=350.0,
        latency_p95_ms=780.0,
        total_cases=1,
        repeats=3,
    )
    case_result = CaseRunResult(
        case_id="case-101",
        role="Senior SRE",
        question="How do you handle an incident?",
        answer="I open an incident channel and triage.",
        repeats=3,
        dimension_scores={"communication": [4, 4, 4]},
        dimension_variances={"communication": 0.0},
        dimension_stds={"communication": 0.0},
        dimension_agreements={"communication": 1.0},
        dimension_maes={"communication": 0.0},
        evidence_validity_rates={"communication": 1.0},
        evidence_quotes={"communication": ["open an incident channel"]},
        is_injection=False,
    )
    return EvalRunResult(
        run_id="run-test-01",
        timestamp="2026-10-14T12:00:00Z",
        model_name="gemini-2.0-flash",
        prompt_version="v1",
        golden_set_path="evals/golden/scorer.jsonl",
        case_count=1,
        repeats=3,
        summary_metrics=summary,
        case_results=[case_result],
        passed_thresholds=True,
    )


def test_markdown_and_json_generation():
    eval_result = _build_sample_eval_result()

    md = generate_markdown_report(eval_result)
    assert "# Evaluation Report — v1" in md
    assert "run-test-01" in md
    assert "88.0%" in md
    assert "Senior SRE" in md

    js = generate_json_report(eval_result)
    assert "run-test-01" in js
    assert "gemini-2.0-flash" in js


def test_history_ledger_operations(tmp_path):
    history_file = tmp_path / "history.json"
    assert load_run_history(history_file) == []

    eval_result = _build_sample_eval_result()
    append_run_history(eval_result, history_file=history_file)

    history = load_run_history(history_file)
    assert len(history) == 1
    assert history[0]["run_id"] == "run-test-01"

    baseline = get_latest_baseline(history_file=history_file, prompt_version="v1")
    assert baseline is not None
    assert baseline.agreement_rate_within_one == 0.88
