"""注册 SandboxWorkerPool 的 Prometheus 指标回调。

在 Celery worker 进程启动后被调用一次，将 pool 的运行时指标
注入到 prometheus_client 的 CollectorRegistry 中。
"""

import logging

from acoj_sandbox.client import SandboxClient

logger = logging.getLogger(__name__)


def init() -> None:
    """初始化 pool 指标采集，兼容 SandboxClient lazy pool 创建。"""
    from app.platform.observability.metrics import (
        register_sandbox_pool_metrics,
    )

    def _register(pool) -> None:
        register_sandbox_pool_metrics(pool)
        logger.info("sandbox pool metrics registered: pool=%p", id(pool))

    register_callback = getattr(SandboxClient, "register_pool_created_callback", None)
    if register_callback is not None:
        register_callback(_register)
        return

    pool = SandboxClient._pool
    if pool is not None:
        _register(pool)
