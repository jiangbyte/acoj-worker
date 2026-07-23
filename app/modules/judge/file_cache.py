"""Judge 文件缓存层：SHA256 内容寻址 + ETag 版本校验 + LRU/TTL 清理。

核心反查策略：
  - SHA256 寻址（有 input_sha256）：缓存命中即有效，不反查远端。
    sha256==内容指纹，远端删改不影响缓存正确性。
  - 名称寻址（无 input_sha256）：60s freshness 窗口后 HeadObject 反查，
    404 → 删脏缓存并回退 input_inline，ETag 不匹配 → 重新下载。

写入全部通过 os.replace 原子操作，多线程安全。
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.core.config.settings import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

# ── 配置 ──

_cache_dir = Path(settings.storage.cache_dir)
CACHE_ROOT = _cache_dir if _cache_dir.is_absolute() else PROJECT_ROOT / _cache_dir
CACHE_ROOT = CACHE_ROOT.resolve()

CACHE_ENABLED = settings.storage.cache_enabled
CACHE_MAX_BYTES = settings.storage.cache_max_mb * 1024 * 1024
CACHE_TTL_SECONDS = settings.storage.cache_ttl_seconds
REVALIDATE_INTERVAL = 60  # 名称寻址 freshness 窗口（秒）
TOUCH_COOLDOWN = 60       # meta last_accessed_at 更新冷却（秒）
LRU_GRACE_PERIOD = 60     # LRU 不淘汰最近 N 秒内访问的文件
EVICT_TARGET_RATIO = 0.8  # LRU 淘汰到上限的 80%

_CACHE_INITIALIZED = False
_CACHE_INIT_LOCK = threading.Lock()
_KEY_LOCKS: dict[str, threading.RLock] = {}
_KEY_LOCKS_LOCK = threading.Lock()


def _ensure_cache_root():
    global _CACHE_INITIALIZED
    if _CACHE_INITIALIZED:
        return
    with _CACHE_INIT_LOCK:
        if not _CACHE_INITIALIZED:
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            _CACHE_INITIALIZED = True


def _key_lock(key: str) -> threading.RLock:
    with _KEY_LOCKS_LOCK:
        lock = _KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _KEY_LOCKS[key] = lock
        return lock


@contextmanager
def _try_key_lock(key: str):
    lock = _key_lock(key)
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def _temp_sibling(path: Path) -> Path:
    suffix = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
    return path.with_name(f"{path.name}.tmp.{suffix}")


# ── 缓存寻址 ──


def _cache_key(sha256: str, object_name: str) -> str:
    if sha256:
        return f"sha256:{sha256}"
    return f"name:{object_name}"


def _data_path(key: str) -> Path:
    return CACHE_ROOT / key[:2] / key


def _meta_path(key: str) -> Path:
    return CACHE_ROOT / key[:2] / f"{key}.meta.json"


# ── 主接口 ──


def resolve_or_download(object_name: str, sha256: str = "") -> Path | None:
    """查缓存 → 版本校验 → 下载 → 写入缓存 → 返回本地路径。

    返回 None 表示远端文件不存在且无缓存可用（调用方应回退 input_inline）。
    """
    if not CACHE_ENABLED:
        return _download_direct(object_name)

    _ensure_cache_root()
    key = _cache_key(sha256, object_name)
    with _key_lock(key):
        return _resolve_or_download_locked(object_name, sha256, key)


def _resolve_or_download_locked(object_name: str, sha256: str, key: str) -> Path | None:
    dpath = _data_path(key)
    mpath = _meta_path(key)

    # ── 1. SHA256 寻址：内容即证明，不反查 ──
    if sha256 and dpath.exists():
        _touch_meta(mpath)
        logger.debug("Cache HIT (sha256): %s", key)
        return dpath

    # ── 2. 名称寻址：freshness 窗口内信任缓存 ──
    if not sha256 and dpath.exists():
        meta = _read_meta(mpath)
        if meta and (time.time() - meta.get("last_validated_at", 0)) < REVALIDATE_INTERVAL:
            _touch_meta(mpath)
            logger.debug("Cache HIT (name, fresh): %s", key)
            return dpath

    # ── 3. 缓存未命中 / freshness 过期 → 反查远端 ──
    from app.platform.storage.manager import get_storage
    storage = get_storage()

    head = _head_or_none(storage, object_name)

    # 3a. 远端文件已不存在
    if head is None:
        if sha256 and dpath.exists():
            # SHA256 寻址：缓存内容是判题指定要的，保留
            _touch_meta(mpath)
            logger.info("远端文件已删除，使用 SHA256 缓存: %s", object_name)
            return dpath
        # 名称寻址：清除脏缓存
        if dpath.exists():
            _remove_entry(key)
            logger.info("远端文件已删除，清除脏缓存: %s", object_name)
        return None

    # 3b. 缓存命中 + ETag 匹配
    remote_etag = str(head.get("etag", ""))
    if dpath.exists():
        meta = _read_meta(mpath)
        if meta and meta.get("etag") == remote_etag:
            _update_meta(mpath, {
                "last_validated_at": time.time(),
                "last_accessed_at": time.time(),
            })
            logger.debug("Cache HIT (name, etag match): %s", key)
            return dpath
        if meta and meta.get("etag") and meta["etag"] != remote_etag:
            logger.info("远端内容已变更: %s etag=%s", object_name, remote_etag)
        _remove_entry(key)

    # 3c. 下载 + 校验 + 写入缓存
    content = _download(storage, object_name)

    if not sha256:
        sha256 = hashlib.sha256(content).hexdigest()
    else:
        actual = hashlib.sha256(content).hexdigest()
        if actual != sha256:
            raise RuntimeError(
                f"SHA256 mismatch for {object_name}: "
                f"expected={sha256}, actual={actual}"
            )

    _store(key, content, sha256, remote_etag, object_name)
    return _data_path(key)


def invalidate(object_name: str, sha256: str = ""):
    """强制删除缓存条目（供外部管理接口调用）。"""
    if not CACHE_ENABLED:
        return
    key = _cache_key(sha256, object_name)
    _remove_entry(key, acquire_lock=True)
    logger.info("缓存已失效: %s", key)


def purge_expired():
    """清理所有超过 TTL 未访问的缓存文件。"""
    if not CACHE_ENABLED:
        return
    _ensure_cache_root()
    if not CACHE_ROOT.exists():
        return
    now = time.time()
    removed = 0
    for meta_file in CACHE_ROOT.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            if now - meta.get("last_accessed_at", 0) > CACHE_TTL_SECONDS:
                key = _key_from_meta_path(meta_file)
                if key:
                    with _try_key_lock(key) as acquired:
                        if acquired:
                            _remove_entry(key, acquire_lock=False)
                            removed += 1
        except Exception:
            continue
    if removed:
        logger.info("TTL 过期清理: 删除 %d 个文件", removed)


# ── 内部 ──


def _store(key: str, content: bytes, sha256: str, etag: str, object_name: str):
    """原子写入缓存文件 + meta 文件，随后触发 LRU 检查。"""
    with _key_lock(key):
        dpath = _data_path(key)
        mpath = _meta_path(key)
        dpath.parent.mkdir(parents=True, exist_ok=True)

        tmp_data = _temp_sibling(dpath)
        tmp_meta = _temp_sibling(mpath)

        now = time.time()
        tmp_data.write_bytes(content)
        os.replace(tmp_data, dpath)

        meta = {
            "etag": etag,
            "sha256": sha256,
            "size_bytes": len(content),
            "object_name": object_name,
            "cached_at": now,
            "last_accessed_at": now,
            "last_validated_at": now,
        }
        with open(tmp_meta, "w") as f:
            json.dump(meta, f)
        os.replace(tmp_meta, mpath)

    logger.debug("缓存写入: %s (%d bytes)", key, len(content))
    _evict_lru_if_needed(0)


def _download(storage, object_name: str) -> bytes:
    if not hasattr(storage, "download_bytes"):
        raise RuntimeError(
            f"Storage {type(storage).__name__} does not support download_bytes"
        )
    return storage.download_bytes(object_name)


def _head_or_none(storage, object_name: str) -> dict | None:
    if not hasattr(storage, "head_object"):
        return None
    try:
        return storage.head_object(object_name)
    except Exception:
        logger.warning("HeadObject 失败: %s", object_name, exc_info=True)
        return None


def _read_meta(mpath: Path) -> dict | None:
    try:
        return json.loads(mpath.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _update_meta(mpath: Path, updates: dict):
    meta = _read_meta(mpath)
    if meta is None:
        return
    meta.update(updates)
    _write_meta(mpath, meta)


def _write_meta(mpath: Path, meta: dict):
    tmp = _temp_sibling(mpath)
    try:
        mpath.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(meta, f)
        os.replace(tmp, mpath)
    except (FileNotFoundError, OSError):
        _unlink(tmp)


def _touch_meta(mpath: Path):
    """惰性更新 last_accessed_at（冷却期内跳过）。"""
    meta = _read_meta(mpath)
    if meta is None:
        return
    now = time.time()
    if now - meta.get("last_accessed_at", 0) < TOUCH_COOLDOWN:
        return
    meta["last_accessed_at"] = now
    _write_meta(mpath, meta)


def _remove_entry(key: str, *, acquire_lock: bool = False):
    if acquire_lock:
        with _key_lock(key):
            _remove_entry(key, acquire_lock=False)
        return
    dpath = _data_path(key)
    mpath = _meta_path(key)
    _unlink(dpath)
    _unlink(mpath)


def _unlink(p: Path):
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def _key_from_meta_path(meta_file: Path) -> str | None:
    """从 meta 文件路径提取 cache key。

    CACHE_ROOT/ab/sha256:abc.meta.json → "sha256:abc"
    """
    name = meta_file.name  # e.g. "sha256:abc.meta.json"
    if name.endswith(".meta.json"):
        return name[: -len(".meta.json")]
    return None


# ── LRU 淘汰 ──


def _evict_lru_if_needed(new_size: int):
    total = _calculate_total_size()
    if total + new_size <= CACHE_MAX_BYTES:
        return
    logger.info("缓存超限: %d / %d bytes, 触发 LRU 淘汰", total + new_size, CACHE_MAX_BYTES)
    _evict_lru(int(total + new_size - CACHE_MAX_BYTES * EVICT_TARGET_RATIO))


def _evict_lru(need_bytes: int):
    """按 last_accessed_at 升序淘汰，跳过 LRU_GRACE_PERIOD 内的文件。"""
    entries = _collect_stats()
    now = time.time()
    candidates = [e for e in entries if now - e["last_accessed_at"] > LRU_GRACE_PERIOD]
    candidates.sort(key=lambda x: x["last_accessed_at"])

    freed = 0
    for entry in candidates:
        if freed >= need_bytes:
            break
        with _try_key_lock(entry["key"]) as acquired:
            if not acquired:
                continue
            _remove_entry(entry["key"], acquire_lock=False)
            freed += entry["size"]
            logger.info("LRU 淘汰: %s (%d bytes)", entry["key"], entry["size"])

    if freed:
        logger.info("LRU 淘汰完成: 释放 %d / %d bytes", freed, need_bytes)


def _collect_stats() -> list[dict]:
    """扫描所有 meta 返回 [{key, size, last_accessed_at}, ...]。"""
    if not CACHE_ROOT.exists():
        return []
    entries = []
    for meta_file in CACHE_ROOT.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            key = _key_from_meta_path(meta_file)
            if key:
                entries.append({
                    "key": key,
                    "size": meta.get("size_bytes", 0),
                    "last_accessed_at": meta.get("last_accessed_at", 0),
                })
        except Exception:
            continue
    return entries


def _calculate_total_size() -> int:
    total = 0
    if not CACHE_ROOT.exists():
        return 0
    for meta_file in CACHE_ROOT.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            total += meta.get("size_bytes", 0)
        except Exception:
            continue
    return total


# ── 降级路径（缓存禁用时直接下载） ──


def _download_direct(object_name: str) -> Path | None:
    from app.platform.storage.manager import get_storage

    storage = get_storage()
    if not hasattr(storage, "download_bytes"):
        return None
    content = storage.download_bytes(object_name)
    tmp_dir = Path(tempfile.gettempdir()) / "acoj-worker-direct"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local = tmp_dir / object_name.replace("/", "_")
    tmp = _temp_sibling(local)
    tmp.write_bytes(content)
    os.replace(tmp, local)
    return local
