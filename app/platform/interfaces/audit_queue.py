from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditEvent:
    resource_type: str
    action: str
    method: str
    path: str
    status_code: int
    account_id: str | None
    account_type: str | None
    request_id: str | None
    ip: str | None
    user_agent: str | None


@runtime_checkable
class AuditQueueProtocol(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def enqueue(self, event: AuditEvent) -> bool: ...
