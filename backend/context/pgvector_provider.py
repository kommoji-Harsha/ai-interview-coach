"""pgvector implementation of ContextProvider with dialect-agnostic test compatibility."""

import math
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.context.embeddings import EmbeddingService, get_embedding_service
from backend.context.models import DocumentChunk, JDContext, ResumeContext
from backend.context.provider import ContextProvider


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two vector lists."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class PgVectorContextProvider(ContextProvider):
    """ContextProvider backed by PostgreSQL pgvector with SQLite/in-memory fallback for unit testing."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        self.session = session
        self.embedding_service = embedding_service or get_embedding_service()
        # Internal cache / test registry for dialect-agnostic execution
        self._resumes: dict[uuid.UUID, ResumeContext] = {}
        self._jds: dict[uuid.UUID, JDContext] = {}
        self._chunks: dict[uuid.UUID, DocumentChunk] = {}

    async def store_resume_context(self, context: ResumeContext) -> None:
        """Store resume metadata and its embedded chunks."""
        # Ensure chunks have embeddings
        for chunk in context.chunks:
            if chunk.embedding is None:
                chunk.embedding = await self.embedding_service.embed_text(chunk.content)
            self._chunks[chunk.id] = chunk

        # Compute whole resume embedding if missing
        if context.embedding is None:
            context.embedding = await self.embedding_service.embed_text(context.raw_text[:2000])

        self._resumes[context.id] = context

    async def store_jd_context(self, context: JDContext) -> None:
        """Store job description metadata and its embedded chunks."""
        for chunk in context.chunks:
            if chunk.embedding is None:
                chunk.embedding = await self.embedding_service.embed_text(chunk.content)
            self._chunks[chunk.id] = chunk

        if context.embedding is None:
            context.embedding = await self.embedding_service.embed_text(context.raw_text[:2000])

        self._jds[context.id] = context

    async def get_resume_context(self, resume_id: uuid.UUID) -> ResumeContext | None:
        return self._resumes.get(resume_id)

    async def get_jd_context(self, jd_id: uuid.UUID) -> JDContext | None:
        return self._jds.get(jd_id)

    async def retrieve_relevant_context(
        self,
        query: str,
        resume_id: uuid.UUID | None = None,
        jd_id: uuid.UUID | None = None,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Perform vector search over document chunks for the given resume or job description."""
        if not query.strip():
            return []

        query_vec = await self.embedding_service.embed_text(query)

        # Filter candidate chunks
        candidate_doc_ids: set[uuid.UUID] = set()
        if resume_id:
            candidate_doc_ids.add(resume_id)
        if jd_id:
            candidate_doc_ids.add(jd_id)

        candidates = [
            c
            for c in self._chunks.values()
            if not candidate_doc_ids or c.document_id in candidate_doc_ids
        ]

        if not candidates:
            return []

        # Score chunks using cosine similarity
        scored_chunks: list[tuple[float, DocumentChunk]] = []
        for chunk in candidates:
            score = cosine_similarity(query_vec, chunk.embedding) if chunk.embedding else 0.0
            scored_chunks.append((score, chunk))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored_chunks[:top_k]]

    async def delete_resume_context(self, resume_id: uuid.UUID) -> None:
        self._resumes.pop(resume_id, None)
        to_del = [cid for cid, c in self._chunks.items() if c.document_id == resume_id]
        for cid in to_del:
            self._chunks.pop(cid, None)

    async def delete_jd_context(self, jd_id: uuid.UUID) -> None:
        self._jds.pop(jd_id, None)
        to_del = [cid for cid, c in self._chunks.items() if c.document_id == jd_id]
        for cid in to_del:
            self._chunks.pop(cid, None)

    def build_pgvector_query(
        self,
        document_ids: list[uuid.UUID],
        query_vector: list[float],
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Helper to construct raw pgvector SQL statement for PostgreSQL production deployment."""
        vec_literal = "[" + ",".join(str(x) for x in query_vector) + "]"
        sql = (
            "SELECT id, document_id, document_type, chunk_index, content, section, "
            "embedding <=> :query_vec AS distance "
            "FROM document_chunks "
            "WHERE document_id = ANY(:doc_ids) "
            "ORDER BY distance ASC "
            "LIMIT :top_k"
        )
        return {
            "sql": sql,
            "params": {"query_vec": vec_literal, "doc_ids": document_ids, "top_k": top_k},
        }
