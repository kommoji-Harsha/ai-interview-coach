"""Golden set loader for JSONL evaluation files."""

import json
from pathlib import Path

from evals.runner.models import GoldenCase


def load_golden_set(
    file_path: str | Path,
    include_deprecated: bool = False,
) -> list[GoldenCase]:
    """Load a golden set from a JSONL file.

    Each line in the JSONL file must be a valid JSON object matching the GoldenCase
    schema (either flat with role, question, answer, human_scores or nested input/expected).

    Args:
        file_path: Path to the .jsonl file.
        include_deprecated: If False, ignores cases marked with "deprecated": true.

    Returns:
        List of validated GoldenCase instances.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If JSON parsing or schema validation fails on any line.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Golden set file not found: {path.resolve()}")

    cases: list[GoldenCase] = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("//") or line_str.startswith("#"):
                continue

            try:
                raw_data = json.loads(line_str)
            except json.JSONDecodeError as err:
                raise ValueError(
                    f"Invalid JSON on line {line_num} in {path.name}: {err}\nLine: {line_str}"
                ) from err

            try:
                case = GoldenCase.model_validate(raw_data)
            except Exception as err:
                raise ValueError(
                    f"Schema validation error on line {line_num} in {path.name}: {err}"
                ) from err

            if case.deprecated and not include_deprecated:
                continue

            cases.append(case)

    return cases
