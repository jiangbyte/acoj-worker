from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transactional(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    if session.in_transaction():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return
    async with session.begin():
        yield session
