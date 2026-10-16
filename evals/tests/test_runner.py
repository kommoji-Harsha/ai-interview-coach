"""Tests for eval runner execution and N-repeat scoring."""

import pytest

from backend.agents.scorer import ScorerAgent
from evals.runner.agent_runner import MockEvaluationGateway, score_case_n_times
from evals.runner.config import EvalConfig
from evals.runner.models import GoldenCase
from evals.runner.run_eval import run_evaluation


@pytest.mark.asyncio
async def test_score_case_n_times_with_mock_gateway():
    agent = ScorerAgent(gateway=MockEvaluationGateway())
    case = GoldenCase(
        id="run-t-01",
        role="Backend Engineer",
        question="How does Redis persistence work?",
        answer="Redis provides RDB snapshots at periodic intervals and AOF logging that logs every write operation.",
        human_scores={"relevance": 5, "technical_depth": 4},
    )

    result, records = await score_case_n_times(agent, case, repeats=3)

    assert result.case_id == "run-t-01"
    assert result.repeats == 3
    assert len(records) == 3

    # Check that dimensions were scored 3 times
    for dim in ["relevance", "technical_depth"]:
        assert len(result.dimension_scores[dim]) == 3
        assert result.dimension_variances[dim] == 0.0  # mock is deterministic
        assert result.dimension_agreements[dim] == 1.0


@pytest.mark.asyncio
async def test_full_evaluation_flow(tmp_path):
    config = EvalConfig(repeats=2, agreement_threshold=0.80)
    result = await run_evaluation(
        golden_path="evals/golden/ci_subset.jsonl",
        repeats=2,
        prompt_version="v1",
        mock=True,
        config=config,
        output_dir=tmp_path / "reports",
    )

    assert result.case_count == 5
    assert result.repeats == 2
    assert result.summary_metrics.agreement_rate_within_one >= 0.80
    assert result.passed_thresholds is True
    assert len(result.threshold_failures) == 0

    # Ensure reports were generated in tmp_path / "reports"
    files = list((tmp_path / "reports").iterdir())
    json_reports = [
        f for f in files if f.suffix == ".json" and f.name.startswith("eval_")
    ]
    md_reports = [f for f in files if f.suffix == ".md" and f.name.startswith("eval_")]
    history_file = tmp_path / "reports" / "history.json"

    assert len(json_reports) == 1
    assert len(md_reports) == 1
    assert history_file.is_file()
