import logging

from app.core.config.settings import settings
from app.modules.judge import sandbox_config
from app.modules.judge.config import JudgeSettings
from app.modules.judge.sandbox_config import (
    build_cgroup_config,
    build_isolation_config,
    create_sandbox_client,
)


def _patch_judge(monkeypatch, **kwargs) -> JudgeSettings:
    cfg = JudgeSettings(**kwargs)
    monkeypatch.setattr(sandbox_config, "get_judge_settings", lambda: cfg)
    return cfg


def test_build_sandbox_runtime_config(monkeypatch):
    _patch_judge(
        monkeypatch,
        sandbox_enable_namespaces=True,
        sandbox_rootfs_path="/srv/rootfs",
        sandbox_enable_cgroup=True,
        sandbox_cgroup_version="v2",
        sandbox_cgroup_base_path="/sys/fs/cgroup/acoj",
    )

    isolation = build_isolation_config()
    cgroup = build_cgroup_config()

    assert isolation.enable_namespaces is True
    assert isolation.rootfs_path == "/srv/rootfs"
    assert cgroup.enabled is True
    assert cgroup.version == "v2"
    assert cgroup.base_path == "/sys/fs/cgroup/acoj"


def test_create_sandbox_client_uses_capacity_settings(monkeypatch):
    _patch_judge(
        monkeypatch,
        sandbox_worker_pool_size=3,
        sandbox_borrow_timeout_seconds=1.5,
        sandbox_max_queue_wait_seconds=2.0,
        sandbox_allow_emergency_worker=False,
        sandbox_request_timeout_seconds=12.0,
        sandbox_queue_wait_warn_seconds=2.5,
        sandbox_health_check_timeout_seconds=0.7,
        sandbox_compilation_cache_enabled=True,
    )
    monkeypatch.setattr(sandbox_config, "_capacity_warning_logged", False)

    client = create_sandbox_client(languages=object())

    assert client.pool_size == 3
    assert client._borrow_timeout == 1.5
    assert client._max_queue_wait_seconds == 2.0
    assert client._request_timeout == 12.0
    assert client._queue_wait_warn_seconds == 2.5
    assert client._health_check_timeout == 0.7
    assert client.allow_emergency_worker is False
    assert client.compilation_cache_enabled is True


def test_create_sandbox_client_warns_when_pool_capacity_will_queue(monkeypatch, caplog):
    monkeypatch.setattr(settings.celery, "worker_concurrency", 4)
    _patch_judge(
        monkeypatch,
        sandbox_standard_parallelism=4,
        sandbox_worker_pool_size=6,
    )
    monkeypatch.setattr(sandbox_config, "_capacity_warning_logged", False)

    with caplog.at_level(logging.WARNING, logger="app.modules.judge.sandbox_config"):
        create_sandbox_client(languages=object())

    assert "pool_size=6" in caplog.text
    assert "expected_peak_requests=16" in caplog.text
