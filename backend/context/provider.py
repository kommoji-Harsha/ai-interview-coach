"""Abstract ContextProvider interface for document retrieval and vector search."""

import uuid
from abc import ABC, abstractmethod

from backend.context.models import DocumentChunk, JDContext, ResumeContext


class ContextProvider(ABC):
    """Interface defining operations for persisting and retrieving context documents."""

    @abstractmethod
    async def store_resume_context(self, context: ResumeContext) -> None:
        """Persist a parsed and chunked resume context."""
        ...

    @abstractmethod
    async def store_jd_context(self, context: JDContext) -> None:
        """Persist a parsed and chunked job description context."""
        ...

    @abstractmethod
    async def get_resume_context(self, resume_id: uuid.UUID) -> ResumeContext | None:
        """Retrieve full resume context by ID."""
        ...

    @abstractmethod
    async def get_jd_context(self, jd_id: uuid.UUID) -> JDContext | None:
        """Retrieve full job description context by ID."""
        ...

    @abstractmethod
    async def retrieve_relevant_context(
        self,
        query: str,
        resume_id: uuid.UUID | None = None,
        jd_id: uuid.UUID | None = None,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Perform semantic similarity search over document chunks.

        Filters chunks by the specified resume_id and/or jd_id and returns the top_k
        most relevant chunks ordered by descending similarity score.
        """
        ...

    @abstractmethod
    async def delete_resume_context(self, resume_id: uuid.UUID) -> None:
        """Delete resume context and all associated chunks."""
        ...

    @abstractmethod
    async def delete_jd_context(self, jd_id: uuid.UUID) -> None:
        """Delete job description context and all associated chunks."""
        ...
