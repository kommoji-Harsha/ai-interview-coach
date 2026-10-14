"""Server-side audio transcription endpoint."""

import os
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.api.deps import get_current_user
from backend.api.deps_gateway import get_gateway
from backend.api.schemas import TranscribeResponse
from backend.config import Settings, get_settings
from backend.db.models import User
from backend.gateway.client import LLMGateway, LLMUnavailableError
from backend.safety.input_screen import validate_input

router = APIRouter()

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm",
    ".wav",
    ".wave",
    ".mp3",
    ".m4a",
    ".ogg",
    ".mp4",
    ".flac",
    ".oga",
}

ALLOWED_MIME_PREFIXES = ("audio/", "video/webm")

NOISE_PATTERN = re.compile(
    r"(?i)(\[[^\]]*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)[^\]]*\]|"
    r"\([^\)]*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)[^\)]*\)|"
    r"\*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)\*)"
)


def clean_transcript(text: str) -> str:
    """Sanitize and clean up transcription output.

    Removes common audio noise tags (e.g. [silence], [inaudible], (cough)),
    normalizes unicode, removes control characters, and collapses whitespace.
    """
    if not text:
        return ""

    # Remove noise brackets and markers
    cleaned = NOISE_PATTERN.sub("", text)

    # Unicode normalization and control character stripping
    cleaned = validate_input(cleaned, field_name="text")

    # Collapse repeated whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


@router.post("/transcribe", response_model=TranscribeResponse)
@router.post("", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: Annotated[UploadFile | None, File()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    user: User = Depends(get_current_user),
    gateway: LLMGateway = Depends(get_gateway),
    settings: Settings = Depends(get_settings),
) -> TranscribeResponse:
    """Transcribe user-recorded audio to text using OpenAI Whisper API.

    Handles audio file size checks, content type validation, and cleans
    noisy transcription artifacts gracefully.
    """
    upload_file = audio or file
    if upload_file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing audio file. Please upload an audio file in the 'audio' form field.",
        )

    # Validate file extension and MIME type
    filename = upload_file.filename or "recording.webm"
    _, ext = os.path.splitext(filename.lower())
    content_type = (upload_file.content_type or "").lower()

    is_valid_ext = ext in ALLOWED_AUDIO_EXTENSIONS
    is_valid_mime = any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES)

    if not is_valid_ext and not is_valid_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio format. Supported formats: WebM, WAV, MP3, M4A, OGG.",
        )

    # Read audio bytes and check length
    contents = await upload_file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty.",
        )

    if len(contents) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file exceeds maximum allowed size of 25 MB.",
        )

    try:
        result = await gateway.transcribe(
            audio_bytes=contents,
            filename=filename,
            content_type=content_type or "audio/webm",
            language="en",
            model=settings.whisper_model,
        )
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transcription service unavailable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transcribe audio: {exc}",
        ) from exc

    # Clean noisy transcription output
    cleaned_text = clean_transcript(result.text)

    return TranscribeResponse(
        text=cleaned_text,
        duration_seconds=result.duration_seconds,
        language=result.language,
    )
