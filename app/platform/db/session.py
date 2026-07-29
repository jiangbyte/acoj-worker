from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config.settings import settings
from app.platform.observability.tracing import init_tracing

engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> None:
    global engine, async_session_factory
    if engine is not None:
        return
    engine_kwargs: dict[str, object] = {"echo": settings.db.echo}
    if not settings.db.url.startswith("sqlite"):
        engine_kwargs["pool_size"] = settings.db.pool_size
        engine_kwargs["max_overflow"] = settings.db.max_overflow
        engine_kwargs["pool_timeout"] = settings.db.pool_timeout_seconds
        engine_kwargs["pool_recycle"] = settings.db.pool_recycle_seconds
        engine_kwargs["pool_pre_ping"] = settings.db.pool_pre_ping
    engine = create_async_engine(settings.db.url, **engine_kwargs)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    if settings.observability.enabled and settings.observability.db_observability_enabled:
        init_tracing(engine=engine)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if async_session_factory is None:
        init_engine()
    if async_session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
    return async_session_factory


async def close_engine() -> None:
    global engine, async_session_factory
    if engine is not None:
        await engine.dispose()
        engine = None
        async_session_factory = None
