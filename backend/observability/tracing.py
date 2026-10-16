"""OpenTelemetry tracing setup and instrumentation helpers."""

from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from backend.config import get_settings

_TRACER_PROVIDER: TracerProvider | None = None


def init_tracer_provider(
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
    processor_override: Any = None,
    force_reinit: bool = False,
) -> TracerProvider:
    """Initialize or retrieve the global TracerProvider."""
    global _TRACER_PROVIDER

    if _TRACER_PROVIDER is not None and not force_reinit:
        if processor_override is not None:
            _TRACER_PROVIDER.add_span_processor(processor_override)
        return _TRACER_PROVIDER

    settings = get_settings()
    name = service_name or settings.otel_service_name
    endpoint = otlp_endpoint if otlp_endpoint is not None else settings.otel_exporter_otlp_endpoint

    resource = Resource.create({"service.name": name})
    provider = TracerProvider(resource=resource)

    if processor_override:
        provider.add_span_processor(processor_override)
    elif endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    # Set as global trace provider
    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider
    return provider


def get_tracer(name: str = "ai-interview-coach") -> Tracer:
    """Return an OpenTelemetry Tracer instance."""
    if _TRACER_PROVIDER is None:
        init_tracer_provider()
    return trace.get_tracer(name)


def setup_tracing(app: FastAPI | None = None) -> None:
    """Setup tracing provider and auto-instrument FastAPI app if provided."""
    init_tracer_provider()
    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="healthz,metrics",
        )
