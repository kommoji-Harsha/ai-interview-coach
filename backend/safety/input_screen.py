"""Pre-LLM input validation and sanitization for untrusted inputs."""

import re
import unicodedata
from dataclasses import dataclass, field

from backend.safety.injection import PromptInjectionError, scan_for_injection

MAX_LENGTHS: dict[str, int] = {
    "resume": 10_000,
    "jd": 5_000,
    "job_description": 5_000,
    "text": 10_000,
}


class SafetyError(Exception):
    """Base exception for input safety violations."""

    pass


class InputTooLongError(SafetyError):
    """Raised when an input exceeds the configured character limit."""

    pass


@dataclass
class ScreeningResult:
    is_safe: bool
    clean_text: str
    violations: list[str] = field(default_factory=list)


def validate_input(text: str, field_name: str = "text", max_length: int | None = None) -> str:
    """Validate length, normalize unicode, and strip unsafe control characters.

    Args:
        text: Untrusted raw text.
        field_name: Context category (e.g., 'resume', 'jd').
        max_length: Optional explicit length override.

    Returns:
        Sanitized and normalized text string.

    Raises:
        InputTooLongError: If text exceeds allowed character limit.
    """
    limit = max_length if max_length is not None else MAX_LENGTHS.get(field_name, 10_000)
    if len(text) > limit:
        raise InputTooLongError(f"{field_name} exceeds maximum length of {limit} characters")

    # Unicode normalization (NFKC decomposes compatibility chars, standardizes homoglyphs)
    normalized = unicodedata.normalize("NFKC", text)

    # Strip null bytes and control characters (preserve newline, carriage return, tab)
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)

    return sanitized


def screen_text(
    text: str,
    field_name: str = "text",
    max_length: int | None = None,
    raise_on_violation: bool = True,
) -> ScreeningResult:
    """Validate and screen untrusted text against prompt-injection attacks.

    Args:
        text: Untrusted input text.
        field_name: Field type ('resume', 'jd', etc.).
        max_length: Optional character limit override.
        raise_on_violation: Whether to raise PromptInjectionError if an attack is detected.

    Returns:
        ScreeningResult containing safety status, clean text, and any violations.
    """
    clean = validate_input(text, field_name=field_name, max_length=max_length)
    violations = scan_for_injection(clean)

    if violations and raise_on_violation:
        raise PromptInjectionError(
            f"Prompt injection detected in {field_name}: {', '.join(violations)}",
            violations=violations,
        )

    return ScreeningResult(
        is_safe=len(violations) == 0,
        clean_text=clean,
        violations=violations,
    )
