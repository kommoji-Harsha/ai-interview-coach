"""Skill-gap analysis comparing Job Description requirements to resume content."""

import re

from backend.context.models import SkillGapItem, SkillGapReport

# Common technical and soft skills taxonomy for canonical matching
CANONICAL_SKILL_SYNONYMS: dict[str, list[str]] = {
    "python": ["python", "python3", "asyncio", "django", "fastapi", "flask"],
    "fastapi": ["fastapi", "starlette", "rest api", "restful api"],
    "postgresql": ["postgresql", "postgres", "psql", "relational database", "sql", "rdbms"],
    "docker": ["docker", "containerization", "containers", "docker-compose"],
    "kubernetes": ["kubernetes", "k8s", "container orchestration"],
    "redis": ["redis", "in-memory cache", "caching"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "system design": [
        "system design",
        "distributed systems",
        "microservices",
        "high availability",
    ],
    "ci/cd": ["ci/cd", "continuous integration", "github actions", "gitlab ci", "jenkins"],
    "typescript": ["typescript", "ts", "javascript", "react", "next.js"],
    "react": ["react", "react.js", "next.js", "frontend"],
    "sql": ["sql", "database queries", "relational databases"],
    "git": ["git", "version control", "github", "gitlab"],
    "grpc": ["grpc", "protobuf", "protocol buffers", "rpc"],
    "kafka": ["kafka", "message queue", "event streaming", "rabbitmq"],
    "testing": ["pytest", "unit testing", "integration testing", "tdd", "automated tests"],
    "linux": ["linux", "unix", "bash", "shell scripting"],
    "security": ["oauth", "jwt", "authentication", "authorization", "owasp"],
}


def _extract_skills_from_text(text: str) -> list[str]:
    """Extract candidate skills and technical requirements mentioned in text."""
    lower_text = text.lower()
    extracted: list[str] = []

    # Check for canonical skills
    for skill, aliases in CANONICAL_SKILL_SYNONYMS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lower_text) for alias in aliases):
            extracted.append(skill)

    # Check for additional skills/keywords listed after bullets or commas
    bullet_matches = re.findall(
        r"(?:requirements?|skills?|technologies|proficient in|experience with)[:\s]+([^\n.]+)",
        lower_text,
        re.IGNORECASE,
    )
    for b in bullet_matches:
        parts = [p.strip() for p in re.split(r"[,;/•\n]", b) if p.strip()]
        for p in parts:
            if len(p) >= 2 and len(p) <= 25 and not any(ch in p for ch in "<>{}[]"):
                clean_skill = p.strip()
                if clean_skill not in extracted:
                    extracted.append(clean_skill)

    return list(dict.fromkeys(extracted))


def _find_evidence_in_resume(resume_text: str, skill: str) -> tuple[str, str | None]:
    """Find whether skill is matched, partial, or missing, and return evidence snippet."""
    resume_lower = resume_text.lower()
    aliases = CANONICAL_SKILL_SYNONYMS.get(skill.lower(), [skill.lower()])

    # Exact match check
    for alias in aliases:
        pattern = rf"([^.\n]*\b{re.escape(alias)}\b[^.\n]*)"
        match = re.search(pattern, resume_lower, re.IGNORECASE)
        if match:
            # Found exact evidence
            start, end = match.span()
            raw_evidence = resume_text[start:end].strip()
            return "matched", raw_evidence or f"Mention of {alias} in resume"

    # Partial match check (e.g. general category or close substring)
    if " " in skill:
        parts = skill.split()
        for p in parts:
            if len(p) > 3 and p in resume_lower:
                return "partial", f"Related experience with '{p}' mentioned"

    return "missing", None


def analyze_skill_gap(
    resume_text: str,
    jd_text: str,
    role_title: str = "Target Role",
) -> SkillGapReport:
    """Compare Job Description requirements against resume content.

    Returns a structured SkillGapReport with matched, partial, and missing skills,
    an overall match score (0.0 to 1.0), and actionable recommendations.
    """
    jd_skills = _extract_skills_from_text(jd_text)
    if not jd_skills:
        # Default fallback standard requirements if none detected in text
        jd_skills = ["python", "system design", "sql", "testing", "git"]

    details: list[SkillGapItem] = []
    matched: list[str] = []
    partial: list[str] = []
    missing: list[str] = []

    for skill in jd_skills:
        status, evidence = _find_evidence_in_resume(resume_text, skill)
        item = SkillGapItem(
            skill=skill,
            status=status,
            importance="required",
            evidence=evidence,
            notes=f"Identified from JD requirements for {role_title}.",
        )
        details.append(item)

        if status == "matched":
            matched.append(skill)
        elif status == "partial":
            partial.append(skill)
        else:
            missing.append(skill)

    # Compute match score: matched = 1.0, partial = 0.5
    total = len(jd_skills)
    score = (len(matched) * 1.0 + len(partial) * 0.5) / total if total > 0 else 0.0
    match_score = round(min(1.0, max(0.0, score)), 2)

    # Strengths summary
    if matched:
        strengths_summary = f"Strong alignment in core areas: {', '.join(matched[:5])}."
    else:
        strengths_summary = "Limited direct keyword alignment found with the required skills."

    # Recommendations
    recommendations: list[str] = []
    if missing:
        recommendations.append(
            f"Address missing key requirements in interview preparation: {', '.join(missing[:4])}."
        )
    if partial:
        recommendations.append(
            f"Elaborate on related experience for partial matches: {', '.join(partial[:3])}."
        )
    if match_score >= 0.8:
        recommendations.append(
            "Candidate demonstrates high technical fit for the role requirements."
        )
    elif match_score < 0.5:
        recommendations.append(
            "Focus initial interview turns on foundational competencies and role expectations."
        )

    return SkillGapReport(
        role_title=role_title,
        match_score=match_score,
        matched_skills=matched,
        missing_skills=missing,
        partial_skills=partial,
        details=details,
        strengths_summary=strengths_summary,
        recommendations=recommendations,
    )
