"""Tests for server-side audio transcription endpoint."""

import struct
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from backend.api.transcription import clean_transcript
from backend.gateway.client import LLMUnavailableError
from backend.gateway.models import TranscriptionResult


def create_sample_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate a valid in-memory PCM WAV audio fixture."""
    num_samples = int(sample_rate * duration_seconds)
    data_size = num_samples * 2  # 16-bit mono = 2 bytes per sample
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,  # PCM
        1,  # Format 1 = PCM
        1,  # 1 channel (mono)
        sample_rate,
        sample_rate * 2,
        2,  # 2 bytes per sample
        16,  # 16 bits per sample
        b"data",
        data_size,
    )
    return header + (b"\x00" * data_size)


@pytest.fixture
def sample_wav_bytes() -> bytes:
    return create_sample_wav(duration_seconds=1.5)


def test_clean_transcript_removes_noise_markers():
    noisy = "[silence] In my previous role at Acme [inaudible], I led the backend team [cough]."
    cleaned = clean_transcript(noisy)
    assert cleaned == "In my previous role at Acme , I led the backend team ."

    noisy_parentheses = "I resolved the issue (laughter) and deployed to prod (inaudible)."
    cleaned2 = clean_transcript(noisy_parentheses)
    assert cleaned2 == "I resolved the issue and deployed to prod ."

    noisy_asterisks = "We increased throughput *noise* by forty percent *applause*."
    cleaned3 = clean_transcript(noisy_asterisks)
    assert cleaned3 == "We increased throughput by forty percent ."


def test_clean_transcript_pure_noise():
    noisy = "[silence] [inaudible] *cough* (laughter)"
    cleaned = clean_transcript(noisy)
    assert cleaned == ""


def test_clean_transcript_normalizes_unicode_and_controls():
    text_with_null = "Architected\x00 distributed\x0b microservices\x0c."
    cleaned = clean_transcript(text_with_null)
    assert cleaned == "Architected distributed microservices."


async def test_transcribe_audio_happy_path(
    client: AsyncClient, auth_headers: dict, sample_wav_bytes: bytes
):
    files = {
        "audio": ("answer.wav", sample_wav_bytes, "audio/wav"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert data["text"] == "In my previous role at Acme, I led a distributed engineering team."
    assert data["duration_seconds"] == 12.5
    assert data["language"] == "en"


async def test_transcribe_audio_field_name_file(
    client: AsyncClient, auth_headers: dict, sample_wav_bytes: bytes
):
    # Support uploading using 'file' field name as well
    files = {
        "file": ("recording.webm", sample_wav_bytes, "audio/webm"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "In my previous role at Acme, I led a distributed engineering team."


async def test_transcribe_audio_requires_auth(client: AsyncClient, sample_wav_bytes: bytes):
    files = {
        "audio": ("recording.wav", sample_wav_bytes, "audio/wav"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files)
    assert resp.status_code == 401


async def test_transcribe_audio_empty_file(client: AsyncClient, auth_headers: dict):
    files = {
        "audio": ("empty.wav", b"", "audio/wav"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


async def test_transcribe_audio_missing_file(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/voice/transcribe", files={}, headers=auth_headers)
    assert resp.status_code == 400
    assert "missing audio file" in resp.json()["detail"].lower()


async def test_transcribe_audio_unsupported_format(client: AsyncClient, auth_headers: dict):
    files = {
        "audio": ("document.txt", b"plain text content", "text/plain"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 400
    assert "unsupported audio format" in resp.json()["detail"].lower()


async def test_transcribe_audio_exceeds_max_size(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    from backend.api import transcription

    # Temporarily set max size to 100 bytes to test limit without allocating 25 MB
    monkeypatch.setattr(transcription, "MAX_AUDIO_SIZE_BYTES", 100)

    files = {
        "audio": ("large.wav", b"x" * 150, "audio/wav"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 400
    assert "exceeds maximum allowed size" in resp.json()["detail"].lower()


async def test_transcribe_audio_cleans_noisy_transcript(
    app, client: AsyncClient, auth_headers: dict, sample_wav_bytes: bytes
):
    from backend.api.deps_gateway import get_gateway

    mock_gw = app.dependency_overrides[get_gateway]()
    mock_gw.transcribe = AsyncMock(
        return_value=TranscriptionResult(
            text="[silence] I designed the caching layer [cough] with Redis [inaudible].",
            duration_seconds=8.0,
            language="en",
            model="whisper-1",
            provider="openai_compat",
        )
    )

    files = {
        "audio": ("speech.webm", sample_wav_bytes, "audio/webm"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "I designed the caching layer with Redis ."


async def test_transcribe_audio_gateway_unavailable(
    app, client: AsyncClient, auth_headers: dict, sample_wav_bytes: bytes
):
    from backend.api.deps_gateway import get_gateway

    mock_gw = app.dependency_overrides[get_gateway]()
    mock_gw.transcribe = AsyncMock(side_effect=LLMUnavailableError("Whisper API connection error"))

    files = {
        "audio": ("speech.wav", sample_wav_bytes, "audio/wav"),
    }
    resp = await client.post("/api/v1/voice/transcribe", files=files, headers=auth_headers)
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"].lower()
