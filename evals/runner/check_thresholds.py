"""Verification of evaluation results against quality thresholds and regression checks."""

import argparse
import json
import sys
from pathlib import Path

from evals.runner.config import DEFAULT_EVAL_CONFIG, EvalConfig
from evals.runner.models import EvalMetricsSummary


def verify_thresholds(
    metrics: EvalMetricsSummary,
    config: EvalConfig = DEFAULT_EVAL_CONFIG,
    baseline_metrics: EvalMetricsSummary | None = None,
) -> tuple[bool, list[str]]:
    """Verify that evaluation metrics meet all configured quality thresholds.

    Args:
        metrics: The metrics computed from the current evaluation run.
        config: Thresholds configuration.
        baseline_metrics: Optional prior run metrics for regression detection.

    Returns:
        (passed: bool, failure_reasons: list[str])
    """
    failures: list[str] = []

    # 1. Agreement within ±1
    if metrics.agreement_rate_within_one < config.agreement_threshold:
        failures.append(
            f"Agreement rate within ±1 {metrics.agreement_rate_within_one:.1%} fell below "
            f"required threshold {config.agreement_threshold:.1%}"
        )

    # 2. Mean Absolute Error (MAE)
    if metrics.mean_mae > config.max_mae:
        failures.append(
            f"Mean Absolute Error {metrics.mean_mae:.2f} exceeded maximum allowed {config.max_mae:.2f}"
        )

    # 3. Run-to-Run Consistency (Standard Deviation)
    if metrics.mean_run_std > config.max_run_std:
        failures.append(
            f"Run-to-run standard deviation {metrics.mean_run_std:.2f} exceeded threshold {config.max_run_std:.2f}"
        )

    # 4. Evidence Quote Validity
    if metrics.evidence_validity_rate < config.evidence_validity_threshold:
        failures.append(
            f"Evidence validity rate {metrics.evidence_validity_rate:.1%} fell below "
            f"threshold {config.evidence_validity_threshold:.1%}"
        )

    # 5. Injection Resistance Pass Rate
    if metrics.injection_resistance_rate < config.injection_resistance_threshold:
        failures.append(
            f"Prompt injection resistance pass rate {metrics.injection_resistance_rate:.1%} fell below "
            f"required {config.injection_resistance_threshold:.1%}"
        )

    # 6. Cost Per Answer
    if metrics.cost_per_answer_usd > config.max_cost_per_answer_usd:
        failures.append(
            f"Cost per answer ${metrics.cost_per_answer_usd:.4f} exceeded budget limit "
            f"${config.max_cost_per_answer_usd:.4f}"
        )

    # 7. Regression check vs baseline if provided
    if baseline_metrics:
        tol = config.regression_tolerance
        min_allowed_agreement = baseline_metrics.agreement_rate_within_one * (1.0 - tol)
        if metrics.agreement_rate_within_one < min_allowed_agreement:
            failures.append(
                f"Regression detected: agreement {metrics.agreement_rate_within_one:.1%} dropped "
                f"> {tol:.0%} below baseline {baseline_metrics.agreement_rate_within_one:.1%}"
            )

    passed = len(failures) == 0
    return passed, failures


def main() -> int:
    """CLI entrypoint to verify evaluation report file against thresholds."""
    parser = argparse.ArgumentParser(description="Verify evaluation run against thresholds.")
    parser.add_argument("--report", required=True, help="Path to JSON evaluation report file")
    parser.add_argument(
        "--agreement-threshold",
        type=float,
        default=DEFAULT_EVAL_CONFIG.agreement_threshold,
        help="Agreement threshold (default: 0.80)",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"Error: Report file not found: {report_path}", file=sys.stderr)
        return 1

    with open(report_path, encoding="utf-8") as f:
        data = json.load(f)

    summary_data = data.get("summary_metrics", data)
    summary = EvalMetricsSummary.model_validate(summary_data)

    config = EvalConfig(agreement_threshold=args.agreement_threshold)
    passed, failures = verify_thresholds(summary, config=config)

    if passed:
        print(f"[PASS] All evaluation thresholds passed! (Agreement: {summary.agreement_rate_within_one:.1%})")
        return 0
    else:
        print("[FAIL] Evaluation threshold check failed:", file=sys.stderr)
        for fail in failures:
            print(f"  - {fail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
