"""Context management package: parsing, chunking, embeddings, pgvector retrieval, and skill gap analysis."""

from backend.context.chunker import chunk_text
from backend.context.embeddings import (
    DeterministicEmbeddingService,
    EmbeddingService,
    get_embedding_service,
)
from backend.context.models import (
    DocumentChunk,
    ExtractedDocument,
    JDContext,
    ResumeContext,
    SkillGapItem,
    SkillGapReport,
)
from backend.context.parser import DocumentParseError, parse_document
from backend.context.pgvector_provider import PgVectorContextProvider, cosine_similarity
from backend.context.provider import ContextProvider
from backend.context.skill_gap import analyze_skill_gap

__all__ = [
    "ContextProvider",
    "DeterministicEmbeddingService",
    "DocumentChunk",
    "DocumentParseError",
    "EmbeddingService",
    "ExtractedDocument",
    "JDContext",
    "PgVectorContextProvider",
    "ResumeContext",
    "SkillGapItem",
    "SkillGapReport",
    "analyze_skill_gap",
    "chunk_text",
    "cosine_similarity",
    "get_embedding_service",
    "parse_document",
]
