from typing import Iterable, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class DataScopeResolverProtocol(Protocol):
    async def list_dept_and_child_ids(
        self, db: AsyncSession, dept_ids: Iterable[str]
    ) -> list[str]: ...
