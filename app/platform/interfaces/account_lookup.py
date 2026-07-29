from typing import Protocol, runtime_checkable


@runtime_checkable
class AccountLookupProtocol(Protocol):
    async def get_active_account_by_id(self, account_id: str) -> object | None: ...
