"""Tests for Prompt A/B comparison and statistical significance."""

import pytest

from evals.prompt_ab.compare import compare_prompt_versions
from evals.prompt_ab.significance import (
    paired_significance_test,
    wilcoxon_signed_rank_test,
)


def test_wilcoxon_identical_distributions():
    diffs = [0.0, 0.0, 0.0, 0.0, 0.0]
    p_val = wilcoxon_signed_rank_test(diffs)
    assert p_val == 1.0


def test_wilcoxon_clear_difference():
    # v2 is consistently much higher than v1
    v1 = [1.0, 1.2, 1.1, 1.3, 1.0, 1.2, 1.1, 1.3, 1.2, 1.1]
    v2 = [4.0, 4.2, 4.1, 4.5, 4.0, 4.3, 4.1, 4.4, 4.2, 4.3]
    diffs = [b - a for a, b in zip(v1, v2)]
    p_val = wilcoxon_signed_rank_test(diffs)
    assert p_val < 0.05

    result = paired_significance_test(v1, v2, "Agreement Rate", higher_is_better=True)
    assert result.significant is True
    assert result.winner == "v2"
    assert result.delta > 0


def test_paired_significance_lower_is_better():
    # MAE: lower is better
    v1_mae = [1.5, 1.4, 1.6, 1.5, 1.7, 1.5, 1.6, 1.4, 1.5, 1.6]
    v2_mae = [0.4, 0.3, 0.5, 0.4, 0.3, 0.4, 0.5, 0.3, 0.4, 0.3]
    result = paired_significance_test(
        v1_mae, v2_mae, "Score MAE", higher_is_better=False
    )
    assert result.significant is True
    assert result.winner == "v2"  # lower MAE wins


@pytest.mark.asyncio
async def test_compare_prompt_versions_e2e(tmp_path):
    result = await compare_prompt_versions(
        golden_path="evals/golden/ci_subset.jsonl",
        v1="v1",
        v2="v1",
        repeats=2,
        mock=True,
        output_dir=tmp_path / "reports",
    )

    assert result.case_count == 5
    assert result.v1_version == "v1"
    assert result.v2_version == "v1"
    assert len(result.metric_results) == 4
    assert result.overall_winner == "tie"
    assert "No statistically significant difference" in result.recommendation

    # Check that A/B markdown report was generated
    md_files = list((tmp_path / "reports").glob("*_v1_vs_v1.md"))
    assert len(md_files) == 1
