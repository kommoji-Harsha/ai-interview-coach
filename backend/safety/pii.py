"""PII detection and redaction utilities for safe logging and telemetry."""

import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def _luhn_checksum_valid(number_str: str) -> bool:
    """Verify Luhn checksum for possible credit card numbers."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_pii(text: str) -> str:
    """Redact Personally Identifiable Information (email, phone, SSN, credit cards)."""
    if not text:
        return text

    # Redact email addresses
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", text)

    # Redact SSN
    redacted = SSN_RE.sub("[REDACTED_SSN]", redacted)

    # Redact Phone numbers
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)

    # Redact Credit Card numbers that satisfy Luhn checksum
    def _replace_cc(match: re.Match) -> str:
        matched_str = match.group(0)
        digits_only = re.sub(r"\D", "", matched_str)
        if 13 <= len(digits_only) <= 19 and _luhn_checksum_valid(digits_only):
            return "[REDACTED_CREDIT_CARD]"
        return matched_str

    redacted = CREDIT_CARD_CANDIDATE_RE.sub(_replace_cc, redacted)

    return redacted
