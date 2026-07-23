"""文件缓存单元测试 — file_cache 内部函数（需 mock settings 和 storage）。

使用 tmp_path 模拟缓存目录，避免影响真实缓存。
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock


# 在 import file_cache 之前先 mock settings
_cache_dir_patch = patch(
    "app.modules.judge.file_cache.CACHE_ROOT",
    new=MagicMock(),
)
_cache_dir_patch.start()

from app.modules.judge import file_cache

_cache_dir_patch.stop()


def _make_cache(tmp_path):
    """返回 (CACHE_ROOT, module) 使用 tmp_path 作为缓存根。"""
    root = tmp_path / "judge-cache"
    root.mkdir()
    orig_root = file_cache.CACHE_ROOT
    orig_initialized = file_cache._CACHE_INITIALIZED
    file_cache.CACHE_ROOT = root
    file_cache._CACHE_INITIALIZED = True
    file_cache.CACHE_ENABLED = True
    return root


def _restore_cache(orig_root, orig_initialized):
    file_cache.CACHE_ROOT = orig_root
    file_cache._CACHE_INITIALIZED = orig_initialized


# ── cache_key ──


def test_cache_key_sha256():
    assert file_cache._cache_key("abc123", "ignored") == "sha256:abc123"


def test_cache_key_name():
    assert file_cache._cache_key("", "foo/bar.txt") == "name:foo/bar.txt"


# ── data / meta path ──


def test_data_path_structure(tmp_path):
    root = _make_cache(tmp_path)
    try:
        p = file_cache._data_path("sha256:abc123")
        assert p.parent.name == "sh"
        assert p.name == "sha256:abc123"
        assert str(p).startswith(str(root))
    finally:
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


def test_meta_path_structure(tmp_path):
    root = _make_cache(tmp_path)
    try:
        p = file_cache._meta_path("sha256:abc123")
        assert p.name == "sha256:abc123.meta.json"
        assert str(p).startswith(str(root))
    finally:
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


# ── touch_meta ──


def test_touch_meta_updates_timestamp(tmp_path):
    root = _make_cache(tmp_path)
    try:
        key = "sha256:test1"
        dpath = file_cache._data_path(key)
        mpath = file_cache._meta_path(key)
        dpath.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        meta = {"last_accessed_at": now - 1000, "etag": "x"}
        mpath.write_text(json.dumps(meta))

        file_cache._touch_meta(mpath)
        updated = json.loads(mpath.read_text())
        assert updated["last_accessed_at"] > now - 100
    finally:
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


def test_touch_meta_cooldown(tmp_path):
    root = _make_cache(tmp_path)
    try:
        key = "sha256:test2"
        mpath = file_cache._meta_path(key)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        meta = {"last_accessed_at": now - 5, "etag": "x"}  # 5s ago — within cooldown
        mpath.write_text(json.dumps(meta))

        file_cache._touch_meta(mpath)
        updated = json.loads(mpath.read_text())
        assert updated["last_accessed_at"] == now - 5  # 未更新
    finally:
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


# ── LRU eviction ──


def test_lru_evict_basic(tmp_path):
    root = _make_cache(tmp_path)
    old_max = file_cache.CACHE_MAX_BYTES
    old_ratio = file_cache.EVICT_TARGET_RATIO
    try:
        file_cache.CACHE_MAX_BYTES = 150
        file_cache.EVICT_TARGET_RATIO = 0.5

        for i in range(3):
            key = f"name:file{i}"
            dpath = file_cache._data_path(key)
            mpath = file_cache._meta_path(key)
            dpath.parent.mkdir(parents=True, exist_ok=True)
            dpath.write_bytes(b"x" * 100)
            meta = {
                "size_bytes": 100,
                "last_accessed_at": 1000 - i * 100,
                "etag": "",
                "sha256": "",
                "object_name": f"file{i}",
                "cached_at": 1000 - i * 100,
                "last_validated_at": 1000 - i * 100,
            }
            mpath.write_text(json.dumps(meta))

        # _evict_lru_if_needed 应该触发淘汰
        file_cache._evict_lru_if_needed(0)

        remaining = list(root.rglob("*.meta.json"))
        # 至少淘汰 1 个（total=300, max=150, 淘汰到 75）
        assert len(remaining) <= 2
    finally:
        file_cache.CACHE_MAX_BYTES = old_max
        file_cache.EVICT_TARGET_RATIO = old_ratio
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


def test_lru_grace_period(tmp_path):
    root = _make_cache(tmp_path)
    old_max = file_cache.CACHE_MAX_BYTES
    old_grace = file_cache.LRU_GRACE_PERIOD
    try:
        file_cache.CACHE_MAX_BYTES = 50
        file_cache.LRU_GRACE_PERIOD = 3600  # 1h grace

        now = time.time()
        key = "name:protected"
        dpath = file_cache._data_path(key)
        mpath = file_cache._meta_path(key)
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_bytes(b"x" * 100)
        meta = {
            "size_bytes": 100,
            "last_accessed_at": now,
            "etag": "",
            "sha256": "",
            "object_name": "protected",
            "cached_at": now,
            "last_validated_at": now,
        }
        mpath.write_text(json.dumps(meta))

        file_cache._evict_lru_if_needed(0)

        remaining = list(root.rglob("*.meta.json"))
        assert len(remaining) == 1  # grace 期内，未被淘汰
    finally:
        file_cache.CACHE_MAX_BYTES = old_max
        file_cache.LRU_GRACE_PERIOD = old_grace
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


# ── TTL purge ──


def test_purge_expired(tmp_path):
    root = _make_cache(tmp_path)
    old_ttl = file_cache.CACHE_TTL_SECONDS
    try:
        file_cache.CACHE_TTL_SECONDS = 0  # 任何时间戳都过期

        for i in range(2):
            key = f"name:old{i}"
            dpath = file_cache._data_path(key)
            mpath = file_cache._meta_path(key)
            dpath.parent.mkdir(parents=True, exist_ok=True)
            dpath.write_bytes(b"data")
            meta = {
                "size_bytes": 4,
                "last_accessed_at": 1000,
                "etag": "",
                "sha256": "",
                "object_name": f"old{i}",
                "cached_at": 1000,
                "last_validated_at": 1000,
            }
            mpath.write_text(json.dumps(meta))

        file_cache.purge_expired()

        remaining = list(root.rglob("*.meta.json"))
        assert len(remaining) == 0
    finally:
        file_cache.CACHE_TTL_SECONDS = old_ttl
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


# ── SHA256 cache hit (no remote check) ──


def test_sha256_cache_hit_no_revalidate(tmp_path):
    """SHA256 寻址命中后不反查远端。"""
    root = _make_cache(tmp_path)
    old_revalidate = file_cache.REVALIDATE_INTERVAL
    try:
        file_cache.REVALIDATE_INTERVAL = 0  # 即使 freshness 窗口过
        key = "sha256:knownhash"
        dpath = file_cache._data_path(key)
        mpath = file_cache._meta_path(key)
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_bytes(b"cached content")
        meta = {
            "size_bytes": 14,
            "last_accessed_at": time.time(),
            "etag": "",
            "sha256": "knownhash",
            "object_name": "remote_file.dat",
            "cached_at": time.time(),
            "last_validated_at": 0,
        }
        mpath.write_text(json.dumps(meta))

        result = file_cache.resolve_or_download("remote_file.dat", sha256="knownhash")
        assert result == dpath
    finally:
        file_cache.REVALIDATE_INTERVAL = old_revalidate
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)


def test_store_same_key_concurrent_no_tmp_collision(tmp_path):
    root = _make_cache(tmp_path)
    old_max = file_cache.CACHE_MAX_BYTES
    try:
        file_cache.CACHE_MAX_BYTES = 1024 * 1024
        key = "sha256:concurrent"

        def write_one(i):
            file_cache._store(
                key,
                f"content-{i}".encode(),
                "concurrent",
                f"etag-{i}",
                "object.txt",
            )

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(write_one, range(32)))

        dpath = file_cache._data_path(key)
        mpath = file_cache._meta_path(key)
        assert dpath.exists()
        assert mpath.exists()
        meta = json.loads(mpath.read_text())
        assert meta["sha256"] == "concurrent"
        assert not list(root.rglob("*.tmp.*"))
    finally:
        file_cache.CACHE_MAX_BYTES = old_max
        _restore_cache(file_cache.CACHE_ROOT, file_cache._CACHE_INITIALIZED)
