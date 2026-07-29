"""Judge 模块配置（JUDGE__*），不侵入框架 Settings。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.settings import settings


class JudgeSettings(BaseSettings):
    """判题 / sandbox / 测试数据缓存配置。"""

    model_config = SettingsConfigDict(env_prefix="JUDGE__", extra="ignore")

    # Celery 队列与执行参数（由 celery_setup 应用到 celery_app）
    task_default_queue: str = "judge"
    task_default_routing_key: str = "judge.default"
    task_soft_time_limit: int = 300
    task_time_limit: int = 600
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True
    # Contest fairness: prefetch=1 avoids one slot hoarding many long/TLE tasks.
    worker_prefetch_multiplier: int = 1

    # Sandbox pool — size must cover concurrency × standard_parallelism
    sandbox_worker_pool_size: int = 32
    sandbox_borrow_timeout_seconds: float = 0.05
    sandbox_max_queue_wait_seconds: float = 0.0
    sandbox_request_timeout_seconds: float = 120.0
    sandbox_queue_wait_warn_seconds: float = 0.5
    sandbox_health_check_timeout_seconds: float = 1.0
    sandbox_standard_parallelism: int = 4
    sandbox_allow_emergency_worker: bool = False
    sandbox_compilation_cache_enabled: bool = True
    sandbox_compilation_cache_dir: str = "/tmp/acoj-ccache"
    sandbox_compilation_cache_max_mb: int = 512
    sandbox_compilation_cache_ttl_seconds: int = 3600
    sandbox_enable_namespaces: bool = False
    sandbox_rootfs_path: str = ""
    # When rootfs_path is set, RO-bind host toolchain paths into the rootfs.
    sandbox_bind_system_paths: bool = True
    sandbox_isolate_network: bool = True
    sandbox_isolate_ipc: bool = True
    sandbox_isolate_uts: bool = True
    sandbox_private_mounts: bool = True
    sandbox_use_pivot_root: bool = True
    sandbox_bind_workspace: bool = True
    sandbox_enable_cgroup: bool = False
    sandbox_cgroup_version: str = "auto"
    sandbox_cgroup_base_path: str = "/sys/fs/cgroup/acoj-sandbox"
    sandbox_cgroup_v1_memory_base_path: str = ""
    sandbox_cgroup_v1_pids_base_path: str = ""

    # 测试数据本地缓存
    cache_enabled: bool = True
    cache_dir: str = "storage/judge-cache"
    cache_max_mb: int = 512
    cache_ttl_seconds: int = 86400 * 7


def get_judge_settings() -> JudgeSettings:
    """优先读模块配置（lifespan / worker init 注入），否则回退到 env。"""
    cfg = settings.module_configs.get("judge")
    if isinstance(cfg, JudgeSettings):
        return cfg
    return _fallback_judge_settings()


@lru_cache(maxsize=1)
def _fallback_judge_settings() -> JudgeSettings:
    return JudgeSettings()
