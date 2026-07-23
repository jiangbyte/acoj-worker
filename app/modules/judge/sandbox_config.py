"""Sandbox runtime configuration shared by judge modes."""

import logging

from acoj_sandbox import CgroupConfig, IsolationConfig, SandboxClient

from app.core.config.settings import settings

logger = logging.getLogger(__name__)
_capacity_warning_logged = False
_production_warning_logged = False
_metrics_callback_registered = False


def build_isolation_config() -> IsolationConfig:
    celery = settings.celery
    return IsolationConfig(
        enable_namespaces=celery.sandbox_enable_namespaces,
        isolate_network=celery.sandbox_isolate_network,
        isolate_ipc=celery.sandbox_isolate_ipc,
        isolate_uts=celery.sandbox_isolate_uts,
        private_mounts=celery.sandbox_private_mounts,
        rootfs_path=celery.sandbox_rootfs_path,
        use_pivot_root=celery.sandbox_use_pivot_root,
        bind_workspace=celery.sandbox_bind_workspace,
    )


def build_cgroup_config() -> CgroupConfig:
    celery = settings.celery
    return CgroupConfig(
        enabled=celery.sandbox_enable_cgroup,
        version=celery.sandbox_cgroup_version,
        base_path=celery.sandbox_cgroup_base_path,
        v1_memory_base_path=celery.sandbox_cgroup_v1_memory_base_path,
        v1_pids_base_path=celery.sandbox_cgroup_v1_pids_base_path,
    )


def create_sandbox_client(*, languages, client_cls=SandboxClient) -> SandboxClient:
    celery = settings.celery
    _warn_if_pool_capacity_is_lower_than_parallelism()
    _warn_if_runtime_config_is_not_production_hardened()
    _configure_compilation_cache()
    _register_pool_metrics_callback(client_cls)
    return client_cls(
        languages=languages,
        pool_size=celery.sandbox_worker_pool_size,
        borrow_timeout=celery.sandbox_borrow_timeout_seconds,
        allow_emergency_worker=celery.sandbox_allow_emergency_worker,
        max_queue_wait_seconds=celery.sandbox_max_queue_wait_seconds,
        request_timeout=celery.sandbox_request_timeout_seconds,
        queue_wait_warn_seconds=celery.sandbox_queue_wait_warn_seconds,
        health_check_timeout=celery.sandbox_health_check_timeout_seconds,
        compilation_cache_enabled=celery.sandbox_compilation_cache_enabled,
    )


def _warn_if_pool_capacity_is_lower_than_parallelism() -> None:
    global _capacity_warning_logged
    if _capacity_warning_logged:
        return
    celery = settings.celery
    expected_peak = celery.worker_concurrency * max(1, celery.sandbox_standard_parallelism)
    if celery.sandbox_worker_pool_size < expected_peak:
        logger.warning(
            "sandbox worker pool may queue under peak load: pool_size=%d, worker_concurrency=%d, "
            "standard_parallelism=%d, expected_peak_requests=%d",
            celery.sandbox_worker_pool_size,
            celery.worker_concurrency,
            celery.sandbox_standard_parallelism,
            expected_peak,
        )
        _capacity_warning_logged = True


def _configure_compilation_cache() -> None:
    celery = settings.celery
    if not celery.sandbox_compilation_cache_enabled:
        return
    try:
        from acoj_sandbox import compilation_cache

        compilation_cache.configure(
            cache_root=celery.sandbox_compilation_cache_dir,
            max_cache_bytes=celery.sandbox_compilation_cache_max_mb * 1024 * 1024,
            ttl_seconds=celery.sandbox_compilation_cache_ttl_seconds,
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
        from app.platform.observability.metrics import register_sandbox_pool_metrics

        register_sandbox_pool_metrics(pool)

    register(_on_pool_created)
    _metrics_callback_registered = True


def _warn_if_runtime_config_is_not_production_hardened() -> None:
    global _production_warning_logged
    if _production_warning_logged or settings.app.debug:
        return
    celery = settings.celery
    warnings: list[str] = []
    if not celery.sandbox_enable_namespaces:
        warnings.append("namespaces disabled")
    if celery.sandbox_enable_namespaces and not celery.sandbox_rootfs_path:
        warnings.append("namespaces enabled without rootfs_path")
    if not celery.sandbox_enable_cgroup:
        warnings.append("cgroup disabled")
    if warnings:
        logger.warning(
            "sandbox runtime is not production hardened: %s",
            ", ".join(warnings),
        )
    _production_warning_logged = True
