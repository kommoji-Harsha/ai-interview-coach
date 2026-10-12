from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown: clean up gateway connections
    from backend.api.deps_gateway import reset_gateway

    reset_gateway()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    # Include routers
    from backend.api.auth import router as auth_router
    from backend.api.health import router as health_router
    from backend.api.sessions import router as sessions_router

    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_v1_prefix + "/auth", tags=["auth"])
    app.include_router(
        sessions_router, prefix=settings.api_v1_prefix + "/sessions", tags=["sessions"]
    )
    return app


app = create_app()
