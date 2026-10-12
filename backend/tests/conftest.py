"""Shared test fixtures.

Uses SQLite in-memory via aiosqlite so tests don't need PostgreSQL.
Overrides FastAPI dependency injection to use test DB and mocked LLM gateway.
"""

import os
from unittest.mock import AsyncMock, MagicMock

# Ensure required configuration is available for test suite
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-min32chars")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from backend.api.deps_gateway import get_gateway, get_session_manager
from backend.db.models import Base
from backend.db.session import get_db
from backend.gateway.client import LLMGateway
from backend.gateway.models import LLMResult
from backend.main import create_app
from backend.orchestrator.session_manager import SessionManager

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # SQLite doesn't enforce FK by default; turn it on.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Mock LLM gateway fixtures
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = LLMResult(
    content=(
        '{"question": "Tell me about your experience with Python.",'
        ' "topic": "technical", "difficulty": 2,'
        ' "reasoning": "Starting with a relevant technical question"}'
    ),
    model="test-model",
    provider="test",
    input_tokens=100,
    output_tokens=50,
    latency_ms=200,
    cached=False,
)


@pytest.fixture
def mock_gateway():
    """A mocked LLM gateway that returns a canned JSON response."""
    gw = MagicMock(spec=LLMGateway)
    gw.complete = AsyncMock(return_value=MOCK_LLM_RESPONSE)
    return gw


@pytest.fixture
def mock_session_manager(mock_gateway):
    return SessionManager(gateway=mock_gateway)


# ---------------------------------------------------------------------------
# FastAPI app & HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def app(db_engine, mock_gateway, mock_session_manager):
    application = create_app()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_gateway] = lambda: mock_gateway
    application.dependency_overrides[get_session_manager] = lambda: mock_session_manager
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client):
    """Register a test user and return auth headers."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "testpassword123",
            "display_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
