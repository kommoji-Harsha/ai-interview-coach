"""Tests for Golden Set loader and models."""

import json
from pathlib import Path

import pytest

from evals.runner.loader import load_golden_set


def test_load_golden_set_valid(tmp_path: Path):
    sample_file = tmp_path / "valid.jsonl"
    lines = [
        json.dumps(
            {
                "id": "t-001",
                "role": "Backend Engineer",
                "question": "What is an index?",
                "answer": "An index is a B-tree structure that speeds up lookups.",
                "human_scores": {"relevance": 5, "technical_depth": 4},
            }
        ),
        json.dumps(
            {
                "id": "t-002",
                "role": "Frontend Engineer",
                "question": "What is CSS Grid?",
                "answer": "CSS Grid is a two-dimensional layout system.",
                "human_scores": {"communication": 4, "relevance": 5},
                "deprecated": True,
            }
        ),
    ]
    sample_file.write_text("\n".join(lines), encoding="utf-8")

    # By default, deprecated is excluded
    cases = load_golden_set(sample_file)
    assert len(cases) == 1
    assert cases[0].id == "t-001"
    assert cases[0].role == "Backend Engineer"
    assert cases[0].rubric_dimensions == ["relevance", "technical_depth"]
    assert cases[0].jd_text == "Target Role: Backend Engineer"

    # With include_deprecated=True
    all_cases = load_golden_set(sample_file, include_deprecated=True)
    assert len(all_cases) == 2


def test_load_golden_set_nested_format(tmp_path: Path):
    sample_file = tmp_path / "nested.jsonl"
    data = {
        "id": "nest-001",
        "input": {
            "question": "Explain idempotency.",
            "answer": "Idempotent requests produce the same side effect if called repeatedly.",
            "jd_text": "API Engineer",
            "rubric_dimensions": ["technical_depth"],
        },
        "expected": {
            "answer_type": "attempted",
            "scores": {"technical_depth": {"min": 4, "max": 5}},
            "evidence_must_reference": ["same side effect"],
        },
    }
    sample_file.write_text(json.dumps(data), encoding="utf-8")

    cases = load_golden_set(sample_file)
    assert len(cases) == 1
    c = cases[0]
    assert c.id == "nest-001"
    assert c.question == "Explain idempotency."
    assert c.rubric_dimensions == ["technical_depth"]
    target_min, target_max, midpoint = c.get_dimension_target("technical_depth")
    assert target_min == 4.0
    assert target_max == 5.0
    assert midpoint == 4.5


def test_load_golden_set_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_golden_set("non_existent_file.jsonl")


def test_load_golden_set_invalid_json(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.jsonl"
    corrupt_file.write_text("{this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_golden_set(corrupt_file)


def test_golden_set_scorer_file_loads():
    cases = load_golden_set("evals/golden/scorer.jsonl")
    assert len(cases) >= 15
    for case in cases:
        assert case.role
        assert case.question
        assert case.answer
        assert len(case.human_scores) > 0
        assert len(case.rubric_dimensions) > 0


def test_golden_set_ci_subset_file_loads():
    cases = load_golden_set("evals/golden/ci_subset.jsonl")
    assert len(cases) == 5
    injection_cases = [c for c in cases if c.is_injection]
    assert len(injection_cases) == 1
