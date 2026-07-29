from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.core.config.settings import settings
from app.platform.events import emit_sync

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OperationAuditEvent:
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


class OperationAuditQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[OperationAuditEvent] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._worker and not self._worker.done():
                return
            self._queue = asyncio.Queue(maxsize=settings.audit.operation_queue_size)
            self._worker = asyncio.create_task(self._run(), name="operation-audit-writer")

    async def stop(self) -> None:
        async with self._lock:
            queue = self._queue
            worker = self._worker
            self._queue = None
            self._worker = None
        if queue is None or worker is None:
            return

        try:
            await asyncio.wait_for(
                queue.join(),
                timeout=settings.audit.operation_shutdown_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("Timed out waiting for operation audit queue to drain")

        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    def enqueue(self, event: OperationAuditEvent) -> bool:
        queue = self._queue
        if queue is None:
            logger.debug("Operation audit queue is not started; dropping event")
            return False
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Operation audit queue is full; dropping event")
            return False
        return True

    async def _run(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while True:
            event = await queue.get()
            try:
                await _record_operation_audit(event)
            except Exception:
                logger.exception("Failed to write operation audit log")
            finally:
                queue.task_done()


async def _record_operation_audit(event: OperationAuditEvent) -> None:
    """持久化审计事件 — 通过事件总线分发，模块自行订阅处理。"""
    emit_sync("on_audit_event", event=event)


operation_audit_queue = OperationAuditQueue()


async def start_operation_audit_queue() -> None:
    await operation_audit_queue.start()


async def stop_operation_audit_queue() -> None:
    await operation_audit_queue.stop()
