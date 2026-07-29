"""Sandbox runtime configuration shared by judge modes."""

import logging

from acoj_sandbox import CgroupConfig, IsolationConfig, SandboxClient

from app.core.config.settings import settings
from app.modules.judge.config import get_judge_settings

logger = logging.getLogger(__name__)
_capacity_warning_logged = False
_production_warning_logged = False
_metrics_callback_registered = False


def build_isolation_config() -> IsolationConfig:
    cfg = get_judge_settings()
    return IsolationConfig(
        enable_namespaces=cfg.sandbox_enable_namespaces,
        isolate_network=cfg.sandbox_isolate_network,
        isolate_ipc=cfg.sandbox_isolate_ipc,
        isolate_uts=cfg.sandbox_isolate_uts,
        private_mounts=cfg.sandbox_private_mounts,
        rootfs_path=cfg.sandbox_rootfs_path,
        use_pivot_root=cfg.sandbox_use_pivot_root,
        bind_workspace=cfg.sandbox_bind_workspace,
    )


def build_cgroup_config() -> CgroupConfig:
    cfg = get_judge_settings()
    return CgroupConfig(
        enabled=cfg.sandbox_enable_cgroup,
        version=cfg.sandbox_cgroup_version,
        base_path=cfg.sandbox_cgroup_base_path,
        v1_memory_base_path=cfg.sandbox_cgroup_v1_memory_base_path,
        v1_pids_base_path=cfg.sandbox_cgroup_v1_pids_base_path,
    )


def create_sandbox_client(*, languages, client_cls=SandboxClient) -> SandboxClient:
    cfg = get_judge_settings()
    _warn_if_pool_capacity_is_lower_than_parallelism()
    _warn_if_runtime_config_is_not_production_hardened()
    _configure_compilation_cache()
    _register_pool_metrics_callback(client_cls)
    return client_cls(
        languages=languages,
        pool_size=cfg.sandbox_worker_pool_size,
        borrow_timeout=cfg.sandbox_borrow_timeout_seconds,
        allow_emergency_worker=cfg.sandbox_allow_emergency_worker,
        max_queue_wait_seconds=cfg.sandbox_max_queue_wait_seconds,
        request_timeout=cfg.sandbox_request_timeout_seconds,
        queue_wait_warn_seconds=cfg.sandbox_queue_wait_warn_seconds,
        health_check_timeout=cfg.sandbox_health_check_timeout_seconds,
        compilation_cache_enabled=cfg.sandbox_compilation_cache_enabled,
    )


def _warn_if_pool_capacity_is_lower_than_parallelism() -> None:
    global _capacity_warning_logged
    if _capacity_warning_logged:
        return
    cfg = get_judge_settings()
    expected_peak = settings.celery.worker_concurrency * max(
        1, cfg.sandbox_standard_parallelism
    )
    if cfg.sandbox_worker_pool_size < expected_peak:
        logger.warning(
            "sandbox worker pool may queue under peak load: pool_size=%d, worker_concurrency=%d, "
            "standard_parallelism=%d, expected_peak_requests=%d",
            cfg.sandbox_worker_pool_size,
            settings.celery.worker_concurrency,
            cfg.sandbox_standard_parallelism,
            expected_peak,
        )
        _capacity_warning_logged = True


def _configure_compilation_cache() -> None:
    cfg = get_judge_settings()
    if not cfg.sandbox_compilation_cache_enabled:
        return
    try:
        from acoj_sandbox import compilation_cache

        compilation_cache.configure(
            cache_root=cfg.sandbox_compilation_cache_dir,
            max_cache_bytes=cfg.sandbox_compilation_cache_max_mb * 1024 * 1024,
            ttl_seconds=cfg.sandbox_compilation_cache_ttl_seconds,
        )
    except Exception:
        logger.exception("failed to configure sandbox compilation cache")


def _register_pool_metrics_callback(client_cls) -> None:
    global _metrics_callback_registered
    if _metrics_callback_registered:
        return
    register = getattr(client_cls, "register_pool_created_callback", None)
    if register is None:
        return

    def _on_pool_created(pool) -> None:
        from app.modules.judge.pool_metrics import register_sandbox_pool_metrics

        register_sandbox_pool_metrics(pool)

    register(_on_pool_created)
    _metrics_callback_registered = True


def _warn_if_runtime_config_is_not_production_hardened() -> None:
    global _production_warning_logged
    if _production_warning_logged or settings.app.debug:
        return
    cfg = get_judge_settings()
    warnings: list[str] = []
    if not cfg.sandbox_enable_namespaces:
        warnings.append("namespaces disabled")
    if cfg.sandbox_enable_namespaces and not cfg.sandbox_rootfs_path:
        warnings.append("namespaces enabled without rootfs_path")
    if not cfg.sandbox_enable_cgroup:
        warnings.append("cgroup disabled")
    if warnings:
        logger.warning(
            "sandbox runtime is not production hardened: %s",
            ", ".join(warnings),
        )
    _production_warning_logged = True
