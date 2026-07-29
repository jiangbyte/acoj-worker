"""框架事件总线 — 模块订阅生命周期事件，框架 emit。

预定义事件:
  - on_config_loaded(config_reader)     -- 配置快照就绪后
  - on_storage_configured               -- 存储配置应用后
  - on_permissions_synced(app)          -- 权限同步完成后
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Coroutine[Any, Any, None] | None]

_subscribers: dict[str, list[EventHandler]] = {}


def subscribe(event_name: str, handler: EventHandler) -> None:
    _subscribers.setdefault(event_name, []).append(handler)


async def emit(event_name: str, **kwargs: Any) -> None:
    for handler in _subscribers.get(event_name, []):
        try:
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Error in event handler %s for event %s", handler, event_name)


def emit_sync(event_name: str, **kwargs: Any) -> None:
    for handler in _subscribers.get(event_name, []):
        try:
            result = handler(**kwargs)
            if inspect.iscoroutine(result):
                logger.warning(
                    "Sync emit %s called async handler %s; result not awaited",
                    event_name, handler,
                )
        except Exception:
            logger.exception("Error in event handler %s for event %s", handler, event_name)
