"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog

# Keys that should never be logged for PII and security protection
FORBIDDEN_LOG_KEYS = {
    "resume",
    "resume_text",
    "jd",
    "jd_text",
    "job_description",
    "answer",
    "candidate_answer",
    "candidate_content",
    "question",
    "prompt",
    "system_prompt",
    "messages",
    "password",
    "access_token",
    "refresh_token",
    "jwt_secret_key",
    "google_api_key",
    "openai_api_key",
}


def pii_scrubber(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Ensure raw user content, prompts, and sensitive credentials are not logged."""
    for key in list(event_dict.keys()):
        if key.lower() in FORBIDDEN_LOG_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog and standard logging for structured output."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        pii_scrubber,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Align stdlib root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Convenience getter for a bound structured logger."""
    return structlog.get_logger(name)
