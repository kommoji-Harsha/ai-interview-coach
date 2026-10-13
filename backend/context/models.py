"""Pydantic models for context extraction, chunking, and skill-gap analysis."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A semantic chunk of a resume or job description with vector embedding metadata."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    document_id: uuid.UUID
    document_type: str  # "resume" or "jd"
    chunk_index: int
    content: str
    embedding: list[float] | None = None
    section: str | None = None
    char_start: int = 0
    char_end: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedDocument(BaseModel):
    """Result of parsing and text extraction from raw document bytes or text."""

    text: str
    filename: str | None = None
    char_count: int
    sections: dict[str, str] = Field(default_factory=dict)


class ResumeContext(BaseModel):
    """Full parsed and embedded context for a candidate resume."""

    id: uuid.UUID
    user_id: uuid.UUID
    label: str | None = None
    filename: str
    raw_text: str
    char_count: int
    chunks: list[DocumentChunk] = Field(default_factory=list)
    parsed_sections: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class JDContext(BaseModel):
    """Full parsed and embedded context for a job description."""

    id: uuid.UUID
    user_id: uuid.UUID
    company: str | None = None
    role_title: str
    raw_text: str
    seniority_level: str | None = None
    char_count: int
    chunks: list[DocumentChunk] = Field(default_factory=list)
    embedding: list[float] | None = None


class SkillGapItem(BaseModel):
    """Evaluation item for a specific skill requirement."""

    skill: str
    status: str  # "matched", "missing", "partial"
    importance: str = "required"  # "required", "preferred", "bonus"
    evidence: str | None = None
    notes: str | None = None


class SkillGapReport(BaseModel):
    """Structured report comparing job description requirements against resume content."""

    role_title: str
    match_score: float = Field(ge=0.0, le=1.0)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    partial_skills: list[str] = Field(default_factory=list)
    details: list[SkillGapItem] = Field(default_factory=list)
    strengths_summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
