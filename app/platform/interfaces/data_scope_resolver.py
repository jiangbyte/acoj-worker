from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class DataScopeResolverProtocol(Protocol):
    async def list_dept_and_child_ids(self, dept_ids: Iterable[str]) -> list[str]: ...
