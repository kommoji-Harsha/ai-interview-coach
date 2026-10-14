"""A/B comparison harness for evaluating two prompt versions on the same golden set."""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from evals.prompt_ab.significance import ABMetricResult, paired_significance_test
from evals.reports.generator import generate_ab_markdown_report
from evals.runner.models import EvalMetricsSummary
from evals.runner.run_eval import run_evaluation


class ABComparisonResult(BaseModel):
    """Aggregate result of an A/B evaluation between two prompt versions."""

    v1_version: str
    v2_version: str
    timestamp: str
    golden_set_path: str
    case_count: int
    repeats: int
    v1_summary: EvalMetricsSummary
    v2_summary: EvalMetricsSummary
    metric_results: list[ABMetricResult] = Field(default_factory=list)
    overall_winner: str = Field(description="'v1', 'v2', or 'tie'")
    recommendation: str


async def compare_prompt_versions(
    golden_path: str | Path,
    v1: str = "v1",
    v2: str = "v2",
    repeats: int = 3,
    mock: bool = False,
    model: str | None = None,
    output_dir: str | Path = "evals/reports",
) -> ABComparisonResult:
    """Run an A/B comparison of prompt version v1 vs v2 on the same golden dataset.

    Args:
        golden_path: Path to the golden dataset JSONL file.
        v1: Baseline prompt version.
        v2: Candidate prompt version.
        repeats: Repeat scoring iterations per case.
        mock: Use mock LLM gateway.
        model: Optional model name.
        output_dir: Destination directory for reports.

    Returns:
        ABComparisonResult containing comparative statistics and promotion recommendation.
    """
    # 1. Run eval on v1
    eval_v1 = await run_evaluation(
        golden_path=golden_path,
        repeats=repeats,
        prompt_version=v1,
        model=model,
        mock=mock,
        output_dir=output_dir,
    )

    # 2. Run eval on v2
    eval_v2 = await run_evaluation(
        golden_path=golden_path,
        repeats=repeats,
        prompt_version=v2,
        model=model,
        mock=mock,
        output_dir=output_dir,
    )

    # 3. Extract paired case distributions
    cases_v1_map = {c.case_id: c for c in eval_v1.case_results}
    cases_v2_map = {c.case_id: c for c in eval_v2.case_results}

    shared_ids = [cid for cid in cases_v1_map if cid in cases_v2_map]

    # Agreement within ±1
    v1_agreements = [
        sum(cases_v1_map[cid].dimension_agreements.values()) / max(len(cases_v1_map[cid].dimension_agreements), 1)
        for cid in shared_ids
    ]
    v2_agreements = [
        sum(cases_v2_map[cid].dimension_agreements.values()) / max(len(cases_v2_map[cid].dimension_agreements), 1)
        for cid in shared_ids
    ]

    # Score MAE
    v1_maes = [
        sum(cases_v1_map[cid].dimension_maes.values()) / max(len(cases_v1_map[cid].dimension_maes), 1)
        for cid in shared_ids
    ]
    v2_maes = [
        sum(cases_v2_map[cid].dimension_maes.values()) / max(len(cases_v2_map[cid].dimension_maes), 1)
        for cid in shared_ids
    ]

    # Score Consistency (Std Dev)
    v1_stds = [
        sum(cases_v1_map[cid].dimension_stds.values()) / max(len(cases_v1_map[cid].dimension_stds), 1)
        for cid in shared_ids
    ]
    v2_stds = [
        sum(cases_v2_map[cid].dimension_stds.values()) / max(len(cases_v2_map[cid].dimension_stds), 1)
        for cid in shared_ids
    ]

    # Evidence Quote Validity
    v1_evidences = [
        sum(cases_v1_map[cid].evidence_validity_rates.values()) / max(len(cases_v1_map[cid].evidence_validity_rates), 1)
        for cid in shared_ids
    ]
    v2_evidences = [
        sum(cases_v2_map[cid].evidence_validity_rates.values()) / max(len(cases_v2_map[cid].evidence_validity_rates), 1)
        for cid in shared_ids
    ]

    metric_results = [
        paired_significance_test(v1_agreements, v2_agreements, "Agreement Rate (+/-1)", higher_is_better=True),
        paired_significance_test(v1_maes, v2_maes, "Score MAE", higher_is_better=False),
        paired_significance_test(v1_stds, v2_stds, "Score Consistency (std)", higher_is_better=False),
        paired_significance_test(v1_evidences, v2_evidences, "Evidence Validity Rate", higher_is_better=True),
    ]

    # Determine overall winner
    v2_wins = sum(1 for m in metric_results if m.winner == "v2")
    v1_wins = sum(1 for m in metric_results if m.winner == "v1")

    if v2_wins > v1_wins:
        overall_winner = "v2"
        recommendation = f"Promote {v2} to active. Statistically significant improvements observed."
    elif v1_wins > v2_wins:
        overall_winner = "v1"
        recommendation = f"Retain {v1}. {v2} demonstrated regression in evaluation metrics."
    else:
        overall_winner = "tie"
        recommendation = f"No statistically significant difference found between {v1} and {v2}. Retain {v1}."

    timestamp = datetime.now(timezone.utc).isoformat()
    ab_result = ABComparisonResult(
        v1_version=v1,
        v2_version=v2,
        timestamp=timestamp,
        golden_set_path=str(Path(golden_path).as_posix()),
        case_count=len(shared_ids),
        repeats=repeats,
        v1_summary=eval_v1.summary_metrics,
        v2_summary=eval_v2.summary_metrics,
        metric_results=metric_results,
        overall_winner=overall_winner,
        recommendation=recommendation,
    )

    # Save A/B Markdown report
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ab_file = out_dir / f"{slug}_{v1}_vs_{v2}.md"
    report_content = generate_ab_markdown_report(ab_result)
    with open(ab_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    return ab_result


def main() -> int:
    """CLI entrypoint for Prompt A/B comparison."""
    parser = argparse.ArgumentParser(description="Run Prompt A/B comparison on golden dataset.")
    parser.add_argument("--golden", default="evals/golden/scorer.jsonl", help="Golden set file path")
    parser.add_argument("--v1", default="v1", help="Baseline prompt version (default: v1)")
    parser.add_argument("--v2", default="v1", help="Candidate prompt version to compare (default: v1)")
    parser.add_argument("--repeats", type=int, default=3, help="Repeats per test case (default: 3)")
    parser.add_argument("--mock", action="store_true", help="Use mock gateway")
    parser.add_argument("--output-dir", default="evals/reports", help="Output directory")

    args = parser.parse_args()

    result = asyncio.run(
        compare_prompt_versions(
            golden_path=args.golden,
            v1=args.v1,
            v2=args.v2,
            repeats=args.repeats,
            mock=args.mock,
            output_dir=args.output_dir,
        )
    )

    print("\n" + "=" * 65)
    print(f"Prompt A/B Comparison: {result.v1_version} vs {result.v2_version}")
    print(f"Cases: {result.case_count} | Repeats: {result.repeats}")
    print("-" * 65)
    for m in result.metric_results:
        sig_str = "Yes" if m.significant else "No"
        print(f"{m.metric:<25} | {m.v1_mean:<7.2f} -> {m.v2_mean:<7.2f} | p={m.p_value:<6.3f} | Sig: {sig_str:<3} | Winner: {m.winner}")
    print("-" * 65)
    print(f"Recommendation: {result.recommendation}")
    print("=" * 65)

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
