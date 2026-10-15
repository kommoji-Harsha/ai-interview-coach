"""Evidence quote validity and verification metrics."""

import re


def _normalize_text(text: str) -> str:
    """Normalize text by lowering case and stripping non-alphanumeric noise."""
    text = text.lower().strip()
    # Replace quotes and multiple whitespace
    text = re.sub(r'["\'`“”]', "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def validate_evidence_quote(
    evidence: str,
    answer: str,
    answer_type: str = "attempted",
    required_phrases: list[str] | None = None,
) -> tuple[bool, str]:
    """Validate that an evidence quote provided by the scorer is grounded in the answer.

    Rules:
    - Evidence cannot be blank.
    - If answer_type is 'no_answer', evidence should indicate 'not addressed' or lack of answer.
    - If answer_type is 'attempted', evidence must be grounded in candidate answer text (exact substring,
      normalized substring, or high lexical overlap).
    - If required_phrases are provided, evidence should reference them.

    Returns:
        (is_valid: bool, reason: str)
    """
    clean_evidence = evidence.strip()
    if not clean_evidence:
        return False, "Evidence quote is empty"

    norm_evidence = _normalize_text(clean_evidence)
    norm_answer = _normalize_text(answer)

    # Check for no_answer condition
    if (
        answer_type == "no_answer"
        or "not addressed" in norm_evidence
        or "no answer" in norm_evidence
    ):
        return True, "Valid non-answer evidence"

    # 1. Direct exact or normalized substring match
    if clean_evidence in answer or norm_evidence in norm_answer:
        return True, "Direct substring match"

    # 2. Check for quoted phrases inside the evidence string
    quotes = re.findall(r'["\']([^"\']{4,})["\']', clean_evidence)
    if quotes:
        for q in quotes:
            if _normalize_text(q) in norm_answer:
                return True, f"Quoted phrase '{q}' found in answer"

    # 3. Check token overlap for paraphrases / excerpted clips
    ev_tokens = set(re.findall(r"\b\w{3,}\b", norm_evidence))
    ans_tokens = set(re.findall(r"\b\w{3,}\b", norm_answer))

    if not ev_tokens:
        return False, "Evidence contains no substantive tokens"

    overlap = ev_tokens.intersection(ans_tokens)
    overlap_ratio = len(overlap) / len(ev_tokens)

    if overlap_ratio >= 0.6:
        return True, f"Lexical overlap grounded in answer ({overlap_ratio:.1%})"

    # 4. Check if required phrases are met
    if required_phrases:
        matched_required = sum(
            1
            for p in required_phrases
            if _normalize_text(p) in norm_evidence or _normalize_text(p) in norm_answer
        )
        if matched_required > 0:
            return True, "Matched required reference phrases"

    return (
        False,
        f"Evidence '{clean_evidence[:60]}...' is not grounded in candidate answer",
    )


def compute_evidence_validity(
    evidence_items: list[str],
    answer: str,
    answer_type: str = "attempted",
    required_phrases: list[str] | None = None,
) -> float:
    """Calculate the fraction of valid evidence quotes for a response."""
    if not evidence_items:
        return 0.0
    valid_count = 0
    for ev in evidence_items:
        is_valid, _ = validate_evidence_quote(ev, answer, answer_type, required_phrases)
        if is_valid:
            valid_count += 1
    return valid_count / len(evidence_items)
