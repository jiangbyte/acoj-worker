"""从共享存储和 MQ 消息加载测试数据，构建 DataRef。

流程：
  input_inline → DataRef.from_data() 直接构造
  input_file + LocalStorage → get_path() 直读
  input_file + Remote → file_cache.resolve_or_download() 缓存层处理

文件生命周期由 file_cache 管理（LRU + TTL + ETag 版本校验），
不再有全局临时文件列表和 per-judge 清理。
"""

import logging
import threading
from pathlib import Path

from acoj_sandbox import DataRef

logger = logging.getLogger(__name__)

_storage = None
_storage_lock = threading.Lock()


def _ensure_storage():
    global _storage
    if _storage is not None:
        return
    with _storage_lock:
        if _storage is None:
            from app.platform.storage.manager import get_storage

            _storage = get_storage()


def resolve_input_ref(test_case: dict) -> DataRef:
    """解析测试点输入数据。"""
    input_file = test_case.get("input_file") or ""
    expected_sha256 = test_case.get("input_sha256") or ""

    if input_file:
        file_path = _resolve_file(input_file, expected_sha256)
        if file_path and file_path.exists():
            ref = DataRef.from_path(str(file_path), compute_hash="always")
            if expected_sha256 and ref.sha256 and ref.sha256 != expected_sha256:
                logger.error(
                    "输入文件 hash 不匹配: %s, expected=%s, actual=%s",
                    input_file,
                    expected_sha256,
                    ref.sha256,
                )
                raise RuntimeError(f"测试数据文件 hash 不匹配: {input_file}")
            return ref
        if input_file:
            logger.warning("输入文件不存在: %s", input_file)

    return DataRef.from_data(test_case.get("input_inline", ""))


def resolve_output_ref(test_case: dict) -> DataRef | None:
    """解析期望输出。"""
    output_file = test_case.get("output_file") or ""
    expected_sha256 = test_case.get("output_sha256") or ""

    if output_file:
        file_path = _resolve_file(output_file, expected_sha256)
        if file_path and file_path.exists():
            ref = DataRef.from_path(str(file_path), compute_hash="always")
            if expected_sha256 and ref.sha256 and ref.sha256 != expected_sha256:
                logger.error(
                    "输出文件 hash 不匹配: %s, expected=%s, actual=%s",
                    output_file,
                    expected_sha256,
                    ref.sha256,
                )
                raise RuntimeError(f"测试数据文件 hash 不匹配: {output_file}")
            return ref
        if output_file:
            logger.warning("输出文件不存在: %s", output_file)

    output_inline = test_case.get("output_inline")
    if output_inline is not None:
        return DataRef.from_data(output_inline)
    return None


def _resolve_file(object_name: str, sha256: str = "") -> Path | None:
    """解析文件路径：LocalStorage 直读，Remote 经缓存层。"""
    _ensure_storage()

    # LocalStorage 快速路径（直读本地文件系统）
    if hasattr(_storage, "get_path"):
        try:
            return _storage.get_path(object_name)
        except ValueError:
            logger.warning("非法的文件路径: %s", object_name)
            return None

    # Remote 路径：走缓存层（下载 → 缓存 → 版本校验）
    from app.modules.judge import file_cache

    return file_cache.resolve_or_download(object_name, sha256)
