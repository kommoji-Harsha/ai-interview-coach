"""Markdown and JSON report generators for single runs and A/B prompt comparisons."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.prompt_ab.compare import ABComparisonResult
    from evals.runner.models import EvalRunResult


def generate_json_report(eval_result: "EvalRunResult") -> str:
    """Format an EvalRunResult as indented JSON string."""
    return eval_result.model_dump_json(indent=2)


def generate_markdown_report(eval_result: "EvalRunResult") -> str:
    """Generate a clean, structured Markdown report from an EvalRunResult."""
    s = eval_result.summary_metrics
    gate_badge = "✅ PASSED" if eval_result.passed_thresholds else "❌ FAILED"

    lines = [
        f"# Evaluation Report — {eval_result.prompt_version}",
        "",
        f"**Run ID:** `{eval_result.run_id}`  |  **Timestamp:** `{eval_result.timestamp}`  |  **Gate Status:** {gate_badge}",
        f"**Model:** `{eval_result.model_name}`  |  **Cases:** {eval_result.case_count}  |  **Repeats:** {eval_result.repeats}",
        f"**Dataset:** `{eval_result.golden_set_path}`",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Result | Target / Threshold | Status |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Agreement Rate (within ±1)** | **{s.agreement_rate_within_one:.1%}** | ≥ 80.0% | {'✅' if s.agreement_rate_within_one >= 0.8 else '❌'} |",
        f"| **Mean Absolute Error (MAE)** | **{s.mean_mae:.2f}** | ≤ 1.00 | {'✅' if s.mean_mae <= 1.0 else '❌'} |",
        f"| **Score Consistency (Std Dev σ)** | **{s.mean_run_std:.2f}** | ≤ 0.50 | {'✅' if s.mean_run_std <= 0.5 else '❌'} |",
        f"| **Evidence Validity Rate** | **{s.evidence_validity_rate:.1%}** | ≥ 80.0% | {'✅' if s.evidence_validity_rate >= 0.8 else '❌'} |",
        f"| **Injection Resistance Rate** | **{s.injection_resistance_rate:.1%}** | 100.0% | {'✅' if s.injection_resistance_rate >= 1.0 else '❌'} |",
        f"| **Cost Per Answer** | **${s.cost_per_answer_usd:.4f}** | ≤ $0.0500 | {'✅' if s.cost_per_answer_usd <= 0.05 else '❌'} |",
        f"| **Total Run Cost** | **${s.total_cost_usd:.4f}** | — | ℹ️ |",
        f"| **Latency p50 / p95** | **{s.latency_p50_ms:.0f}ms / {s.latency_p95_ms:.0f}ms** | < 2s / < 5s | {'✅' if s.latency_p95_ms < 5000 else '⚠️'} |",
        f"| **Unstable Cases (σ > 0.8)** | **{s.unstable_case_count}** | 0 | {'✅' if s.unstable_case_count == 0 else '⚠️'} |",
        "",
    ]

    if not eval_result.passed_thresholds:
        lines.extend([
            "### ❌ Threshold Failures",
            "",
            *[f"- {fail}" for fail in eval_result.threshold_failures],
            "",
        ])

    lines.extend([
        "## Case-by-Case Breakdown",
        "",
        "| Case ID | Role | Dimensions | Agreement (±1) | MAE | σ (Std) | Evidence Valid | Injection Resisted | Unstable |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for case in eval_result.case_results:
        dims_str = ", ".join(case.dimension_scores.keys())
        avg_agr = (
            sum(case.dimension_agreements.values()) / max(len(case.dimension_agreements), 1)
        )
        avg_mae = (
            sum(case.dimension_maes.values()) / max(len(case.dimension_maes), 1)
        )
        avg_std = (
            sum(case.dimension_stds.values()) / max(len(case.dimension_stds), 1)
        )
        avg_ev = (
            sum(case.evidence_validity_rates.values()) / max(len(case.evidence_validity_rates), 1)
        )
        inj_str = (
            ("✅ Yes" if case.injection_resisted else "❌ No")
            if case.is_injection
            else "—"
        )
        unstable_str = "⚠️ Yes" if case.is_unstable else "No"

        lines.append(
            f"| `{case.case_id}` | {case.role or 'N/A'} | {dims_str} | {avg_agr:.1%} | {avg_mae:.2f} | {avg_std:.2f} | {avg_ev:.1%} | {inj_str} | {unstable_str} |"
        )

    lines.append("")
    return "\n".join(lines)


def generate_ab_markdown_report(ab_result: "ABComparisonResult") -> str:
    """Generate prompt A/B Markdown comparison report matching eval_design.md specification."""
    lines = [
        f"# Prompt A/B Report: {ab_result.v1_version} vs {ab_result.v2_version}",
        f"**Date:** {ab_result.timestamp[:10]}  |  **Dataset:** `{ab_result.golden_set_path}`  |  **Cases:** {ab_result.case_count}  |  **Repeats:** {ab_result.repeats}",
        "",
        "| Metric | v1 (mean) | v2 (mean) | Delta | p-value | Significant? | Winner |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for m in ab_result.metric_results:
        sig_badge = "✅ Yes" if m.significant else "❌ No"
        winner_badge = f"**{m.winner}**" if m.winner != "tie" else "—"
        lines.append(
            f"| {m.metric} | {m.v1_mean:.2f} | {m.v2_mean:.2f} | {m.delta:+.2f} | {m.p_value:.3f} | {sig_badge} | {winner_badge} |"
        )

    lines.extend([
        "",
        f"**Recommendation:** {ab_result.recommendation}",
        "",
    ])

    return "\n".join(lines)
