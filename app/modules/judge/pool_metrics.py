"""Sandbox Worker Pool Prometheus 指标（模块内，不侵入 platform.metrics）。"""

from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge, Histogram

from app.platform.observability.metrics import metrics_enabled, registry

logger = logging.getLogger(__name__)

sandbox_pool_workers = Gauge(
    "sandbox_pool_workers",
    "Sandbox pool current worker count (state: available, active, total)",
    ["state"],
    registry=registry,
)
sandbox_pool_borrow_total = Counter(
    "sandbox_pool_borrow_total",
    "Total sandbox worker borrow requests",
    registry=registry,
)
sandbox_pool_borrow_wait_ms = Histogram(
    "sandbox_pool_borrow_wait_ms",
    "Sandbox worker borrow wait time in milliseconds",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000),
    registry=registry,
)
sandbox_pool_emergency_total = Counter(
    "sandbox_pool_emergency_total",
    "Total emergency worker spawns (borrow timeout fallback)",
    registry=registry,
)
sandbox_pool_replaced_total = Counter(
    "sandbox_pool_replaced_total",
    "Total worker replacements (health check failure + max_requests recycle)",
    registry=registry,
)
sandbox_pool_queue_timeout_total = Counter(
    "sandbox_pool_queue_timeout_total",
    "Total sandbox worker queue timeout failures",
    registry=registry,
)


def register_sandbox_pool_metrics(pool) -> None:
    """注入 Prometheus 回调到 SandboxWorkerPool。"""
    if not metrics_enabled():
        return

    last = {
        "borrow_count": 0,
        "emergency_count": 0,
        "replaced_count": 0,
        "queue_timeout_count": 0,
    }

    def on_event(p) -> None:
        s = p.stats()
        sandbox_pool_workers.labels(state="available").set(s["available_count"])
        sandbox_pool_workers.labels(state="active").set(s["active_count"])
        sandbox_pool_workers.labels(state="total").set(s["total_count"])
        borrow_delta = max(0, s["borrow_count"] - last["borrow_count"])
        if borrow_delta:
            sandbox_pool_borrow_total.inc(borrow_delta)
            sandbox_pool_borrow_wait_ms.observe(s.get("borrow_last_wait_ms", 0))
        emergency_delta = max(0, s["emergency_count"] - last["emergency_count"])
        if emergency_delta:
            sandbox_pool_emergency_total.inc(emergency_delta)
        replaced_delta = max(0, s["replaced_count"] - last["replaced_count"])
        if replaced_delta:
            sandbox_pool_replaced_total.inc(replaced_delta)
        queue_timeout_delta = max(
            0,
            s.get("queue_timeout_count", 0) - last["queue_timeout_count"],
        )
        if queue_timeout_delta:
            sandbox_pool_queue_timeout_total.inc(queue_timeout_delta)

        last["borrow_count"] = s["borrow_count"]
        last["emergency_count"] = s["emergency_count"]
        last["replaced_count"] = s["replaced_count"]
        last["queue_timeout_count"] = s.get("queue_timeout_count", 0)

    pool.set_metrics_callback(on_event)


def init() -> None:
    """初始化 pool 指标采集，兼容 SandboxClient lazy pool 创建。"""
    try:
        from acoj_sandbox.client import SandboxClient
    except ImportError:
        logger.debug("acoj_sandbox not available; skip pool metrics init")
        return

    def _register(pool) -> None:
        register_sandbox_pool_metrics(pool)
        logger.info("sandbox pool metrics registered: pool=%s", id(pool))

    register_callback = getattr(SandboxClient, "register_pool_created_callback", None)
    if register_callback is not None:
        register_callback(_register)
        return

    pool = getattr(SandboxClient, "_pool", None)
    if pool is not None:
        _register(pool)
