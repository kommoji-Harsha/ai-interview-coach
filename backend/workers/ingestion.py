"""Background worker tasks for resume and job description ingestion, safety screening, chunking, and embedding."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from backend.context.chunker import chunk_text
from backend.context.embeddings import get_embedding_service
from backend.context.models import JDContext, ResumeContext, SkillGapReport
from backend.context.parser import parse_document
from backend.context.pgvector_provider import PgVectorContextProvider
from backend.context.provider import ContextProvider
from backend.context.skill_gap import analyze_skill_gap
from backend.safety.input_screen import screen_text

logger = structlog.get_logger()


@dataclass
class IngestionJob:
    """Tracks background job state and results."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    job_type: str = "resume_ingestion"
    status: str = "pending"  # "pending", "processing", "completed", "failed"
    user_id: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None
    result: Any | None = None


async def ingest_resume(
    file_content: bytes | str,
    filename: str,
    user_id: uuid.UUID,
    resume_id: uuid.UUID | None = None,
    label: str | None = None,
    context_provider: ContextProvider | None = None,
) -> ResumeContext:
    """Ingestion pipeline for resumes: parse -> safety screen -> chunk -> embed -> persist.

    Args:
        file_content: Raw bytes or string content of the resume (PDF, DOCX, or text).
        filename: Original file name.
        user_id: Owner user ID.
        resume_id: Optional UUID (generates one if None).
        label: User-given label.
        context_provider: Optional ContextProvider instance (defaults to PgVectorContextProvider).

    Returns:
        Persisted ResumeContext object.

    Raises:
        PromptInjectionError: If untrusted resume contains prompt injection patterns.
        InputTooLongError: If resume exceeds character limit.
        DocumentParseError: If document is unreadable.
    """
    resume_uuid = resume_id or uuid.uuid4()
    provider = context_provider or PgVectorContextProvider()
    embedder = get_embedding_service()

    logger.info("ingest_resume_started", resume_id=str(resume_uuid), filename=filename)

    # 1. Parse document (PDF / DOCX / text)
    extracted = parse_document(file_content, filename=filename, field_name="resume")

    # 2. Safety screening for prompt injection
    screen_result = screen_text(extracted.text, field_name="resume", raise_on_violation=True)

    # 3. Chunk text with section-awareness
    chunks = chunk_text(
        text=screen_result.clean_text,
        document_id=resume_uuid,
        document_type="resume",
        chunk_size=500,
        chunk_overlap=100,
        sections=extracted.sections,
    )

    # 4. Generate embeddings for all chunks in batch
    if chunks:
        chunk_texts = [c.content for c in chunks]
        embeddings = await embedder.embed_batch(chunk_texts)
        for chunk, emb in zip(chunks, embeddings, strict=True):
            chunk.embedding = emb

    # 5. Build ResumeContext
    resume_embedding = await embedder.embed_text(screen_result.clean_text[:2000])
    resume_context = ResumeContext(
        id=resume_uuid,
        user_id=user_id,
        label=label or filename,
        filename=filename,
        raw_text=screen_result.clean_text,
        char_count=len(screen_result.clean_text),
        chunks=chunks,
        parsed_sections=extracted.sections,
        embedding=resume_embedding,
    )

    # 6. Persist to ContextProvider
    await provider.store_resume_context(resume_context)
    logger.info(
        "ingest_resume_completed",
        resume_id=str(resume_uuid),
        chunk_count=len(chunks),
    )

    return resume_context


async def ingest_job_description(
    raw_text: str,
    role_title: str,
    user_id: uuid.UUID,
    jd_id: uuid.UUID | None = None,
    company: str | None = None,
    seniority_level: str | None = None,
    context_provider: ContextProvider | None = None,
) -> JDContext:
    """Ingestion pipeline for job descriptions: safety screen -> chunk -> embed -> persist.

    Args:
        raw_text: Full plain text of the job description.
        role_title: Target role title.
        user_id: Owner user ID.
        jd_id: Optional UUID.
        company: Company name.
        seniority_level: Optional seniority level.
        context_provider: ContextProvider instance.

    Returns:
        Persisted JDContext object.
    """
    jd_uuid = jd_id or uuid.uuid4()
    provider = context_provider or PgVectorContextProvider()
    embedder = get_embedding_service()

    logger.info("ingest_jd_started", jd_id=str(jd_uuid), role_title=role_title)

    # 1. Safety screening
    screen_result = screen_text(raw_text, field_name="jd", raise_on_violation=True)

    # 2. Parse & chunk text
    extracted = parse_document(
        screen_result.clean_text, filename="job_description.txt", field_name="jd"
    )
    chunks = chunk_text(
        text=extracted.text,
        document_id=jd_uuid,
        document_type="jd",
        chunk_size=500,
        chunk_overlap=100,
        sections=extracted.sections,
    )

    # 3. Generate embeddings
    if chunks:
        chunk_texts = [c.content for c in chunks]
        embeddings = await embedder.embed_batch(chunk_texts)
        for chunk, emb in zip(chunks, embeddings, strict=True):
            chunk.embedding = emb

    jd_embedding = await embedder.embed_text(extracted.text[:2000])

    # 4. Build JDContext
    jd_context = JDContext(
        id=jd_uuid,
        user_id=user_id,
        company=company,
        role_title=role_title,
        raw_text=extracted.text,
        seniority_level=seniority_level,
        char_count=len(extracted.text),
        chunks=chunks,
        embedding=jd_embedding,
    )

    # 5. Persist
    await provider.store_jd_context(jd_context)
    logger.info("ingest_jd_completed", jd_id=str(jd_uuid), chunk_count=len(chunks))

    return jd_context


async def process_candidate_application(
    resume_id: uuid.UUID,
    jd_id: uuid.UUID,
    context_provider: ContextProvider,
) -> SkillGapReport:
    """Run asynchronous skill gap analysis between an ingested resume and job description."""
    resume = await context_provider.get_resume_context(resume_id)
    if not resume:
        raise ValueError(f"Resume {resume_id} not found in context provider")

    jd = await context_provider.get_jd_context(jd_id)
    if not jd:
        raise ValueError(f"Job description {jd_id} not found in context provider")

    logger.info(
        "skill_gap_analysis_started",
        resume_id=str(resume_id),
        jd_id=str(jd_id),
        role_title=jd.role_title,
    )

    report = analyze_skill_gap(
        resume_text=resume.raw_text,
        jd_text=jd.raw_text,
        role_title=jd.role_title,
    )

    logger.info(
        "skill_gap_analysis_completed",
        match_score=report.match_score,
        matched_count=len(report.matched_skills),
        missing_count=len(report.missing_skills),
    )

    return report


class IngestionWorker:
    """Background worker coordinator managing asynchronous ingestion jobs."""

    def __init__(self, context_provider: ContextProvider | None = None):
        self.context_provider = context_provider or PgVectorContextProvider()
        self.jobs: dict[uuid.UUID, IngestionJob] = {}

    async def run_resume_job(
        self,
        file_content: bytes | str,
        filename: str,
        user_id: uuid.UUID,
        label: str | None = None,
    ) -> IngestionJob:
        """Execute a resume ingestion background job."""
        job = IngestionJob(job_type="resume_ingestion", user_id=user_id, status="processing")
        self.jobs[job.id] = job

        try:
            result = await ingest_resume(
                file_content=file_content,
                filename=filename,
                user_id=user_id,
                label=label,
                context_provider=self.context_provider,
            )
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.result = result
        except Exception as exc:
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_message = str(exc)
            logger.error("resume_job_failed", job_id=str(job.id), error=str(exc))

        return job

    async def run_jd_job(
        self,
        raw_text: str,
        role_title: str,
        user_id: uuid.UUID,
        company: str | None = None,
        seniority_level: str | None = None,
    ) -> IngestionJob:
        """Execute a job description ingestion background job."""
        job = IngestionJob(job_type="jd_ingestion", user_id=user_id, status="processing")
        self.jobs[job.id] = job

        try:
            result = await ingest_job_description(
                raw_text=raw_text,
                role_title=role_title,
                user_id=user_id,
                company=company,
                seniority_level=seniority_level,
                context_provider=self.context_provider,
            )
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.result = result
        except Exception as exc:
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_message = str(exc)
            logger.error("jd_job_failed", job_id=str(job.id), error=str(exc))

        return job
