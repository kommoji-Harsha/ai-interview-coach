from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings


def create_engine(database_url: str | None = None, echo: bool = False):
    url = database_url or get_settings().database_url
    return create_async_engine(url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# Default engine/session for app startup
engine = create_engine()
SessionLocal = create_session_factory(engine)


async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
