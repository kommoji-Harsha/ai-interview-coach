"""Statistical significance testing for Prompt A/B evaluations."""

import math

from pydantic import BaseModel, Field


class ABMetricResult(BaseModel):
    """Result of statistical significance test for a single metric between v1 and v2."""

    metric: str
    v1_mean: float
    v2_mean: float
    delta: float = Field(description="v2_mean - v1_mean")
    p_value: float = Field(description="Two-tailed p-value from paired test")
    significant: bool = Field(description="Whether p_value < alpha")
    winner: str = Field(description="'v1', 'v2', or 'tie'")


def _normal_cdf(z: float) -> float:
    """Standard normal cumulative distribution function using math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def wilcoxon_signed_rank_test(diffs: list[float]) -> float:
    """Pure-Python implementation of Wilcoxon signed-rank test.

    Computes two-tailed p-value using normal approximation for paired differences.
    """
    non_zero = [d for d in diffs if abs(d) > 1e-9]
    n = len(non_zero)
    if n < 3:
        # Not enough paired differences to compute meaningful significance
        return 1.0

    # Rank absolute differences
    abs_diffs = [(abs(d), i, d) for i, d in enumerate(non_zero)]
    abs_diffs.sort(key=lambda x: x[0])

    # Assign ranks with tie handling
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(abs_diffs[j][0] - abs_diffs[i][0]) < 1e-9:
            j += 1
        # Average rank for ties (1-indexed ranks)
        avg_rank = sum(range(i + 1, j + 1)) / (j - i)
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    # Compute sum of ranks for positive differences
    w_pos = sum(ranks[k] for k in range(n) if abs_diffs[k][2] > 0)
    w_neg = sum(ranks[k] for k in range(n) if abs_diffs[k][2] < 0)
    test_stat = min(w_pos, w_neg)

    # Mean and variance under null hypothesis
    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0

    if var_w <= 0:
        return 1.0

    # Continuity correction
    z = (abs(test_stat - mean_w) - 0.5) / math.sqrt(var_w)
    p_val = 2.0 * (1.0 - _normal_cdf(z))
    return min(max(p_val, 0.0), 1.0)


def paired_significance_test(
    samples_v1: list[float],
    samples_v2: list[float],
    metric_name: str,
    higher_is_better: bool = True,
    alpha: float = 0.05,
) -> ABMetricResult:
    """Run a paired statistical test comparing metrics of v1 and v2 on the same test cases.

    Args:
        samples_v1: Metric values for v1 across test cases.
        samples_v2: Metric values for v2 across test cases.
        metric_name: Name of metric (e.g. 'agreement_rate', 'score_mae').
        higher_is_better: True if larger numbers are better, False if lower is better.
        alpha: Significance threshold (default 0.05).

    Returns:
        ABMetricResult containing means, delta, p_value, significance flag, and winner.
    """
    if len(samples_v1) != len(samples_v2) or len(samples_v1) == 0:
        v1_m = sum(samples_v1) / max(len(samples_v1), 1)
        v2_m = sum(samples_v2) / max(len(samples_v2), 1)
        return ABMetricResult(
            metric=metric_name,
            v1_mean=round(v1_m, 4),
            v2_mean=round(v2_m, 4),
            delta=round(v2_m - v1_m, 4),
            p_value=1.0,
            significant=False,
            winner="tie",
        )

    v1_mean = sum(samples_v1) / len(samples_v1)
    v2_mean = sum(samples_v2) / len(samples_v2)
    delta = v2_mean - v1_mean

    diffs = [s2 - s1 for s1, s2 in zip(samples_v1, samples_v2)]

    # Compute p-value using Wilcoxon signed-rank test
    p_value = wilcoxon_signed_rank_test(diffs)
    significant = p_value < alpha

    # Determine winner
    if not significant or abs(delta) < 1e-6:
        winner = "tie"
    elif higher_is_better:
        winner = "v2" if delta > 0 else "v1"
    else:
        winner = "v2" if delta < 0 else "v1"

    return ABMetricResult(
        metric=metric_name,
        v1_mean=round(v1_mean, 4),
        v2_mean=round(v2_mean, 4),
        delta=round(delta, 4),
        p_value=round(p_value, 4),
        significant=significant,
        winner=winner,
    )
