"""Main entry point to execute evaluations on golden datasets."""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.agents.scorer import ScorerAgent
from evals.metrics.aggregator import aggregate_metrics
from evals.reports.generator import generate_json_report, generate_markdown_report
from evals.reports.history import append_run_history
from evals.runner.agent_runner import MockEvaluationGateway, score_case_n_times
from evals.runner.check_thresholds import verify_thresholds
from evals.runner.config import DEFAULT_EVAL_CONFIG, EvalConfig
from evals.runner.loader import load_golden_set
from evals.runner.models import CaseRunResult, EvalRunResult


async def run_evaluation(
    golden_path: str | Path,
    repeats: int = 3,
    prompt_version: str = "v1",
    model: str | None = None,
    mock: bool = False,
    config: EvalConfig = DEFAULT_EVAL_CONFIG,
    output_dir: str | Path = "evals/reports",
) -> EvalRunResult:
    """Run an evaluation suite across a golden set.

    Args:
        golden_path: Path to the .jsonl golden dataset file.
        repeats: Number of times to score each answer.
        prompt_version: Version of the scorer prompt to use (e.g. 'v1').
        model: Optional LLM model override.
        mock: If True, uses MockEvaluationGateway instead of live LLM.
        config: Evaluation configuration and thresholds.
        output_dir: Directory where reports and history are stored.

    Returns:
        EvalRunResult containing full evaluation outcomes.
    """
    cases = load_golden_set(golden_path)
    if not cases:
        raise ValueError(f"No valid test cases found in {golden_path}")

    # Determine whether to use real LLMGateway or MockEvaluationGateway
    has_api_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if mock or not has_api_key:
        gateway: Any = MockEvaluationGateway()
    else:
        from backend.api.deps_gateway import build_gateway

        gateway = build_gateway()

    agent = ScorerAgent(gateway=gateway, version=prompt_version)

    case_results: list[CaseRunResult] = []
    all_execution_records: list[dict] = []

    for case in cases:
        result, records = await score_case_n_times(
            agent=agent,
            case=case,
            repeats=repeats,
            model=model,
        )
        case_results.append(result)
        all_execution_records.extend(records)

    summary = aggregate_metrics(
        case_results=case_results,
        execution_records=all_execution_records,
        repeats=repeats,
    )

    passed, failures = verify_thresholds(summary, config=config)

    timestamp = datetime.now(timezone.utc).isoformat()
    run_id = f"eval-{uuid.uuid4().hex[:8]}"

    eval_result = EvalRunResult(
        run_id=run_id,
        timestamp=timestamp,
        model_name=model or (getattr(gateway, "model", "mock-scorer-llm") if mock else "gemini-2.0-flash"),
        prompt_version=prompt_version,
        golden_set_path=str(Path(golden_path).as_posix()),
        case_count=len(cases),
        repeats=repeats,
        summary_metrics=summary,
        case_results=case_results,
        passed_thresholds=passed,
        threshold_failures=failures,
    )

    # Generate and save reports
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_content = generate_json_report(eval_result)
    md_content = generate_markdown_report(eval_result)

    run_slug = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{prompt_version}"
    json_file = out_path / f"eval_{run_slug}.json"
    md_file = out_path / f"eval_{run_slug}.md"

    with open(json_file, "w", encoding="utf-8") as f:
        f.write(json_content)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Append to history ledger
    append_run_history(eval_result, history_file=out_path / "history.json")

    return eval_result


def main() -> int:
    """CLI entrypoint for running evaluations."""
    parser = argparse.ArgumentParser(description="Run evaluation on AI Interview Coach golden set.")
    parser.add_argument(
        "--golden",
        default="evals/golden/scorer.jsonl",
        help="Path to golden set JSONL file (default: evals/golden/scorer.jsonl)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of times to score each answer (default: 3)",
    )
    parser.add_argument(
        "--prompt-version",
        default="v1",
        help="Prompt version to evaluate (default: v1)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model identifier override",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock gateway for offline testing",
    )
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Exit with non-zero status if metrics fail configured thresholds",
    )
    parser.add_argument(
        "--output-dir",
        default="evals/reports",
        help="Directory to save report artifacts (default: evals/reports)",
    )
    parser.add_argument(
        "--agreement-threshold",
        type=float,
        default=DEFAULT_EVAL_CONFIG.agreement_threshold,
        help="Agreement threshold (default: 0.80)",
    )

    args = parser.parse_args()

    config = EvalConfig(
        repeats=args.repeats,
        prompt_version=args.prompt_version,
        model=args.model,
        agreement_threshold=args.agreement_threshold,
    )

    eval_result = asyncio.run(
        run_evaluation(
            golden_path=args.golden,
            repeats=args.repeats,
            prompt_version=args.prompt_version,
            model=args.model,
            mock=args.mock,
            config=config,
            output_dir=args.output_dir,
        )
    )

    summary = eval_result.summary_metrics
    print("\n" + "=" * 60)
    print(f"Evaluation Complete: {eval_result.run_id}")
    print(f"Cases: {eval_result.case_count} | Repeats: {eval_result.repeats}")
    print(f"Agreement Rate (+/-1): {summary.agreement_rate_within_one:.1%}")
    print(f"Mean Absolute Error: {summary.mean_mae:.2f}")
    print(f"Run-to-run Std Dev:  {summary.mean_run_std:.2f}")
    print(f"Evidence Validity:   {summary.evidence_validity_rate:.1%}")
    print(f"Injection Resistance:{summary.injection_resistance_rate:.1%}")
    print(f"Cost per answer:     ${summary.cost_per_answer_usd:.4f}")
    print(f"Total cost:          ${summary.total_cost_usd:.4f}")
    print(f"Latency p50 / p95:   {summary.latency_p50_ms:.0f}ms / {summary.latency_p95_ms:.0f}ms")
    print("=" * 60)

    if args.check_thresholds and not eval_result.passed_thresholds:
        print("\n[FAIL] CI Threshold Gate FAILED:")
        for failure in eval_result.threshold_failures:
            print(f"  - {failure}")
        return 1

    print("\n[PASS] Evaluation successfully passed quality thresholds!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
