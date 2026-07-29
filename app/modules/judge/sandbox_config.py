"""Sandbox runtime configuration shared by judge modes."""

import logging
from pathlib import Path

from acoj_sandbox import BindMount, CgroupConfig, IsolationConfig, SandboxClient

from app.core.config.settings import settings
from app.modules.judge.config import get_judge_settings

logger = logging.getLogger(__name__)
_capacity_warning_logged = False
_production_warning_logged = False
_metrics_callback_registered = False

# Debian usr-merge: rootfs uses bin/lib/lib64 -> usr/* symlinks; only bind real trees.
_SYSTEM_BIND_CANDIDATES = ("/usr", "/etc", "/proc")


def _system_bind_mounts() -> list[BindMount]:
    mounts: list[BindMount] = []
    for path in _SYSTEM_BIND_CANDIDATES:
        if Path(path).exists():
            # /proc must be writable for some kernel interfaces; toolchains need it.
            read_only = path != "/proc"
            mounts.append(
                BindMount(source=path, target=path, read_only=read_only, recursive=True)
            )
    return mounts


def build_isolation_config() -> IsolationConfig:
    """构建隔离配置。

    namespaces 关闭时（本机/开发默认），强制关闭依赖 mount/net namespace 的选项，
    避免 acosandbox worker 模式下 C++ 等编译莫名失败。
    """
    cfg = get_judge_settings()
    enable_ns = cfg.sandbox_enable_namespaces
    bind_mounts: list[BindMount] = []
    if cfg.sandbox_rootfs_path and cfg.sandbox_bind_system_paths:
        bind_mounts = _system_bind_mounts()
    return IsolationConfig(
        enable_namespaces=enable_ns,
        isolate_network=cfg.sandbox_isolate_network if enable_ns else False,
        isolate_ipc=cfg.sandbox_isolate_ipc if enable_ns else False,
        isolate_uts=cfg.sandbox_isolate_uts if enable_ns else False,
        private_mounts=cfg.sandbox_private_mounts if enable_ns else False,
        rootfs_path=cfg.sandbox_rootfs_path,
        use_pivot_root=cfg.sandbox_use_pivot_root if enable_ns else False,
        bind_workspace=cfg.sandbox_bind_workspace,
        bind_mounts=bind_mounts,
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
