"""Agreement metrics: within ±1 tolerance, MAE, and in-range rate."""

from typing import Any


def compute_agreement_within_one(
    predicted_score: float,
    human_target: float | dict[str, Any],
) -> bool:
    """Check if predicted score is within ±1 of human score or human range.

    If human_target is a number: |predicted - human| <= 1.0.
    If human_target is a dict with min/max: min - 1 <= predicted <= max + 1.
    """
    pred = float(predicted_score)
    if isinstance(human_target, dict):
        min_val = float(human_target.get("min", 1.0))
        max_val = float(human_target.get("max", min_val))
        return (min_val - 1.0) <= pred <= (max_val + 1.0)
    target = float(human_target)
    return abs(pred - target) <= 1.0


def compute_mae(
    predicted_score: float,
    human_target: float | dict[str, Any],
) -> float:
    """Compute absolute error between predicted score and human target midpoint."""
    pred = float(predicted_score)
    if isinstance(human_target, dict):
        min_val = float(human_target.get("min", 1.0))
        max_val = float(human_target.get("max", min_val))
        midpoint = (min_val + max_val) / 2.0
        return abs(pred - midpoint)
    return abs(pred - float(human_target))


def compute_in_range(
    predicted_score: float,
    human_target: float | dict[str, Any],
) -> bool:
    """Check if predicted score falls strictly within the expected range [min, max]."""
    pred = float(predicted_score)
    if isinstance(human_target, dict):
        min_val = float(human_target.get("min", 1.0))
        max_val = float(human_target.get("max", min_val))
        return min_val <= pred <= max_val
    return pred == float(human_target)


def compute_agreement_rate(
    evaluations: list[tuple[float | int, float | int | dict[str, Any]]],
) -> float:
    """Compute agreement within ±1 rate across a list of (predicted, human) pairs.

    Returns:
        Float between 0.0 and 1.0. Returns 1.0 if empty list.
    """
    if not evaluations:
        return 1.0
    matches = sum(
        1 for pred, human in evaluations if compute_agreement_within_one(pred, human)
    )
    return matches / len(evaluations)
