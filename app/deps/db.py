from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.session import get_session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
