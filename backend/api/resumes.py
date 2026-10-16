"""API router for resume uploads and management with strict ownership boundaries and upload validation."""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from backend.api.deps import get_context_provider, get_current_user
from backend.api.schemas import (
    PaginatedResponse,
    ResumeDetailResponse,
    ResumeMetadataResponse,
)
from backend.context.parser import DocumentParseError
from backend.context.provider import ContextProvider
from backend.db.models import User
from backend.safety.injection import PromptInjectionError
from backend.safety.input_screen import InputTooLongError
from backend.workers.ingestion import ingest_resume

router = APIRouter()

MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB per docs/api.md

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt"}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/octet-stream",
}


def validate_file_bytes(content: bytes, filename: str, content_type: str) -> None:
    """Validate file size, extension, MIME type, and magic bytes."""
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(content) > MAX_RESUME_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {MAX_RESUME_SIZE_BYTES // (1024 * 1024)}MB",
        )

    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Allowed formats: PDF, DOCX, TXT.",
        )

    # Magic byte validation
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file: missing %PDF- header magic bytes",
            )
    elif ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX file: missing ZIP PK header magic bytes",
            )


@router.post("", response_model=ResumeMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: Annotated[UploadFile, File(description="Resume file (PDF, DOCX, TXT max 5MB)")],
    label: Annotated[str | None, Form()] = None,
    user: User = Depends(get_current_user),
    context_provider: ContextProvider = Depends(get_context_provider),
) -> ResumeMetadataResponse:
    """Upload, screen, parse, embed, and store a candidate resume."""
    filename = file.filename or "resume.pdf"
    content_type = (file.content_type or "").lower()

    content = await file.read()
    validate_file_bytes(content, filename, content_type)

    try:
        resume_context = await ingest_resume(
            file_content=content,
            filename=filename,
            user_id=user.id,
            label=label.strip() if label else None,
            context_provider=context_provider,
        )
    except PromptInjectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Prompt injection detected in resume: {exc}",
        ) from exc
    except (InputTooLongError, DocumentParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ResumeMetadataResponse(
        id=resume_context.id,
        label=resume_context.label or resume_context.filename,
        filename=resume_context.filename,
        char_count=resume_context.char_count,
        created_at=datetime.now(UTC).isoformat(),
    )


@router.get("", response_model=PaginatedResponse)
async def list_resumes(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    context_provider: ContextProvider = Depends(get_context_provider),
) -> PaginatedResponse:
    """List all resumes belonging strictly to the authenticated user."""
    resumes = await context_provider.list_resumes_for_user(user.id)
    items = [
        ResumeMetadataResponse(
            id=r.id,
            label=r.label or r.filename,
            filename=r.filename,
            char_count=r.char_count,
            created_at=datetime.now(UTC).isoformat(),
        )
        for r in resumes[:limit]
    ]
    return PaginatedResponse(items=items, next_cursor=None)


@router.get("/{resume_id}", response_model=ResumeDetailResponse)
async def get_resume(
    resume_id: uuid.UUID,
    user: User = Depends(get_current_user),
    context_provider: ContextProvider = Depends(get_context_provider),
) -> ResumeDetailResponse:
    """Fetch full resume details with extracted text, verifying ownership."""
    resume = await context_provider.get_resume_context(resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )

    return ResumeDetailResponse(
        id=resume.id,
        label=resume.label or resume.filename,
        filename=resume.filename,
        raw_text=resume.raw_text,
        char_count=resume.char_count,
        created_at=datetime.now(UTC).isoformat(),
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: uuid.UUID,
    user: User = Depends(get_current_user),
    context_provider: ContextProvider = Depends(get_context_provider),
) -> Response:
    """Delete a resume, strictly verifying user ownership."""
    resume = await context_provider.get_resume_context(resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )

    await context_provider.delete_resume_context(resume_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
