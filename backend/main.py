import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from backend.config import get_settings
from backend.observability.logging import configure_logging
from backend.observability.metrics import (
    HTTP_ACTIVE_REQUESTS,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)
from backend.observability.tracing import setup_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown: clean up gateway connections
    from backend.api.deps_gateway import reset_gateway

    reset_gateway()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        path = request.url.path
        if path in ("/metrics", "/healthz"):
            return await call_next(request)

        method = request.method
        HTTP_ACTIVE_REQUESTS.labels(method=method, path=path).inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            HTTP_ACTIVE_REQUESTS.labels(method=method, path=path).dec()
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=path, status_code=str(status_code)
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, path=path, status_code=str(status_code)
            ).observe(duration)

    # Setup OpenTelemetry tracing
    setup_tracing(app)

    # Include routers
    from backend.api.auth import router as auth_router
    from backend.api.health import router as health_router
    from backend.api.metrics import router as metrics_router
    from backend.api.sessions import router as sessions_router
    from backend.api.transcription import router as transcription_router

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router, prefix=settings.api_v1_prefix + "/auth", tags=["auth"])
    app.include_router(
        sessions_router, prefix=settings.api_v1_prefix + "/sessions", tags=["sessions"]
    )
    app.include_router(
        transcription_router, prefix=settings.api_v1_prefix + "/voice", tags=["voice"]
    )
    app.include_router(
        transcription_router,
        prefix=settings.api_v1_prefix + "/transcription",
        tags=["transcription"],
    )
    return app


app = create_app()
