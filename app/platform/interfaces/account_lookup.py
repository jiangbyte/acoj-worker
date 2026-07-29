from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class AccountLookupProtocol(Protocol):
    async def get_active_account_by_id(
        self, db: AsyncSession, account_id: str
    ) -> object | None: ...
