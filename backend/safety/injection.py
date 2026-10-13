"""Prompt-injection detection for untrusted user inputs (resumes, job descriptions)."""

import base64
import binascii
import re
import unicodedata

# Core injection regex patterns (case-insensitive)
INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Direct instruction overrides
    (
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?|context)",
        "Direct instruction override",
    ),
    (
        r"disregard\s+(all\s+)?(previous|prior|above|existing)\s+(instructions?|prompts?|rules?)",
        "Direct instruction override (disregard)",
    ),
    (
        r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        "Direct instruction override (forget)",
    ),
    (
        r"you\s+are\s+now\s+(a|an|the)\b",
        "Role hijack / persona reassignment",
    ),
    (
        r"your\s+new\s+(role|instructions?|task|goal)\s+(is|are)\b",
        "Role reassignment",
    ),
    (
        r"(^|\n)\s*system\s*:\s*",
        "System prompt impersonation",
    ),
    (
        r"(^|\n)\s*assistant\s*:\s*",
        "Assistant message impersonation",
    ),
    # Prompt extraction / leakage
    (
        r"(reveal|show|output|print|display|repeat)\s+(the\s+)?(full\s+)?(system\s+)?(prompt|instructions?|rules?)",
        "Prompt extraction attempt",
    ),
    (
        r"what\s+are\s+your\s+(exact\s+)?(system\s+)?(instructions|rules|system\s+prompt)",
        "Prompt leakage request",
    ),
    (
        r"print\s+them\s+verbatim",
        "Verbatim prompt extraction",
    ),
    # Score manipulation
    (
        r"(give|assign|set)\s+(all\s+)?(score|rating)s?\s+(to|as|=)\s*[45]",
        "Score override attempt",
    ),
    (
        r"override\s+(the\s+)?scor(e|ing)",
        "Scoring override attempt",
    ),
    (
        r"always\s+(score|rate|give)\s+(a\s+)?[45]",
        "Fixed high score directive",
    ),
    (
        r"give\s+this\s+candidate\s+(all\s+)?[45]s?",
        "Candidate score manipulation",
    ),
    (
        r"rate\s+this\s+candidate\s+as\s+[45]",
        "Candidate rating inflation",
    ),
    # Subversion via "Notes to interviewer" / instructions to evaluator
    (
        r"note\s+to\s+(the\s+)?(interviewer|assistant|ai|evaluator|grader|system)\s*:",
        "Interviewer guidance hijack",
    ),
    (
        r"special\s+instructions?\s+for\s+(the\s+)?(interviewer|assistant|ai|evaluator)\s*:",
        "Special instruction hijack",
    ),
    (
        r"do\s+not\s+ask\s+(any\s+)?questions\s+(about|regarding)",
        "Question restriction injection",
    ),
    (
        r"treat\s+this\s+candidate\s+as\s+(having\s+passed|qualified|senior|flawless)",
        "Evaluation bypass instruction",
    ),
    # Delimiter injection & tag escapes
    (
        r"</?(system|instructions?|prompt|user)>",
        "System/Instructions delimiter tag escape",
    ),
    (
        r"</?(resume|job_description|conversation)>",
        "Document context delimiter tag escape",
    ),
    (
        r"```(system|instructions|prompt)",
        "Markdown system block injection",
    ),
    # Hidden command patterns
    (
        r"\[system\s+command\s*:",
        "Bracketed system command syntax",
    ),
    (
        r"human\s*:\s*.*\s*assistant\s*:",
        "Simulated dialog injection",
    ),
]


class PromptInjectionError(ValueError):
    """Raised when an untrusted input contains prompt injection patterns."""

    def __init__(self, message: str, violations: list[str] | None = None):
        super().__init__(message)
        self.violations = violations or []


def _scan_raw_patterns(text: str) -> list[str]:
    """Scan text against regex injection patterns."""
    violations: list[str] = []
    for pattern, desc in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(desc)
    return violations


def _scan_base64_payloads(text: str) -> list[str]:
    """Scan potential base64 substrings for encoded injection commands."""
    violations: list[str] = []
    # Find candidate base64 sequences (at least 16 base64 characters)
    potential_b64 = re.findall(r"\b[A-Za-z0-9+/]{16,}={0,2}\b", text)
    for b64_token in potential_b64:
        # Check padding
        pad_len = len(b64_token) % 4
        padded = b64_token if pad_len == 0 else b64_token + ("=" * (4 - pad_len))
        try:
            decoded_bytes = base64.b64decode(padded, validate=True)
            # Only inspect if it looks like UTF-8 text
            decoded_str = decoded_bytes.decode("utf-8")
            if any(ch in decoded_str for ch in (" ", "\n", "\t")):
                decoded_normalized = unicodedata.normalize("NFKC", decoded_str)
                sub_violations = _scan_raw_patterns(decoded_normalized)
                if sub_violations:
                    violations.extend([f"Base64-encoded: {v}" for v in sub_violations])
        except (binascii.Error, UnicodeDecodeError):
            continue
    return violations


def scan_for_injection(text: str) -> list[str]:
    """Screen text for prompt injection attempts.

    Returns a list of violation descriptions. If empty, the text is clean.
    """
    if not text:
        return []

    # 1. Normalize unicode homoglyphs (NFKC converts e.g. Roman numeral Ⅰ -> I)
    normalized = unicodedata.normalize("NFKC", text)

    # 2. Direct pattern matching
    violations = _scan_raw_patterns(normalized)

    # 3. Base64 payload detection
    b64_violations = _scan_base64_payloads(normalized)
    violations.extend(b64_violations)

    return list(dict.fromkeys(violations))  # preserve unique in order
