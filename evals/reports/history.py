"""Evaluation run history management and historical baseline tracking."""

import json
from pathlib import Path
from typing import Any

from evals.runner.models import EvalMetricsSummary, EvalRunResult


def load_run_history(history_file: str | Path = "evals/reports/history.json") -> list[dict[str, Any]]:
    """Load historical evaluation run summaries from a JSON ledger file.

    Returns empty list if the file does not exist.
    """
    path = Path(history_file)
    if not path.is_file():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def append_run_history(
    eval_result: EvalRunResult,
    history_file: str | Path = "evals/reports/history.json",
) -> None:
    """Append summary record of an evaluation run into the historical JSON file."""
    path = Path(history_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    history = load_run_history(path)

    record = {
        "run_id": eval_result.run_id,
        "timestamp": eval_result.timestamp,
        "prompt_version": eval_result.prompt_version,
        "model_name": eval_result.model_name,
        "golden_set_path": eval_result.golden_set_path,
        "case_count": eval_result.case_count,
        "repeats": eval_result.repeats,
        "passed_thresholds": eval_result.passed_thresholds,
        "summary_metrics": eval_result.summary_metrics.model_dump(),
    }

    history.append(record)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def get_latest_baseline(
    history_file: str | Path = "evals/reports/history.json",
    prompt_version: str | None = None,
) -> EvalMetricsSummary | None:
    """Retrieve the metrics summary of the latest passing evaluation run from history."""
    history = load_run_history(history_file)
    # Search backwards for the most recent passing run
    for entry in reversed(history):
        if entry.get("passed_thresholds"):
            if prompt_version is None or entry.get("prompt_version") == prompt_version:
                metrics_data = entry.get("summary_metrics")
                if metrics_data:
                    return EvalMetricsSummary.model_validate(metrics_data)
    return None
