"""Variance and consistency metrics across repeated evaluation runs."""

import math


def compute_run_variance(scores: list[int | float]) -> float:
    """Calculate sample variance for repeated scores of the same question/dimension.

    Returns:
        Sample variance (N-1 degrees of freedom) if len(scores) > 1, else 0.0.
    """
    if len(scores) <= 1:
        return 0.0
    mean_val = sum(scores) / len(scores)
    squared_diffs = sum((x - mean_val) ** 2 for x in scores)
    return squared_diffs / (len(scores) - 1)


def compute_score_std(scores: list[int | float]) -> float:
    """Calculate sample standard deviation across repeat runs."""
    return math.sqrt(compute_run_variance(scores))


def is_case_unstable(
    dimension_scores: dict[str, list[int]],
    std_threshold: float = 0.8,
) -> bool:
    """Flag a case as unstable if any rubric dimension exhibits high variance.

    According to eval_design.md: A case is flagged as unstable if std(score) > 0.8.
    """
    for scores in dimension_scores.values():
        if compute_score_std(scores) > std_threshold:
            return True
    return False
