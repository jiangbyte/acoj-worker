"""从共享存储和 MQ 消息加载测试数据，构建 DataRef。
文件生命周期：远程下载 → 使用 → 自动清理；本地直接引用。
"""

import atexit
import logging
import shutil
from pathlib import Path

from acoj_sandbox import DataRef

from app.platform.storage.manager import get_storage

logger = logging.getLogger(__name__)

_storage = get_storage()

# 追踪远程下载的临时文件，确保退出时清理
_downloaded_dirs: list[Path] = []


def _cleanup_downloads():
    for d in _downloaded_dirs:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_downloads)


def resolve_input_ref(test_case: dict) -> DataRef:
    """解析测试点输入数据：优先文件路径 + hash 校验，其次内联数据。"""
    input_file = test_case.get("input_file") or ""
    expected_sha256 = test_case.get("input_sha256") or ""

    if input_file:
        file_path = _resolve_file(input_file)
        if file_path and file_path.exists():
            return _build_data_ref(file_path, expected_sha256)
        logger.warning("输入文件不存在: %s", input_file)

    return DataRef.from_data(test_case.get("input_inline", ""))


def resolve_output_ref(test_case: dict) -> DataRef | None:
    """解析期望输出：优先文件路径 + hash 校验，其次内联数据。"""
    output_file = test_case.get("output_file") or ""
    expected_sha256 = test_case.get("output_sha256") or ""

    if output_file:
        file_path = _resolve_file(output_file)
        if file_path and file_path.exists():
            return _build_data_ref(file_path, expected_sha256)
        logger.warning("输出文件不存在: %s", output_file)

    output_inline = test_case.get("output_inline")
    if output_inline is not None:
        return DataRef.from_data(output_inline)
    return None


def _build_data_ref(file_path: Path, expected_sha256: str) -> DataRef:
    """构建 DataRef，如果提供了 hash 则校验完整性。"""
    ref = DataRef.from_path(str(file_path), compute_hash="always")

    if expected_sha256 and ref.sha256 and ref.sha256 != expected_sha256:
        logger.error(
            "文件 hash 不匹配: %s, expected=%s, actual=%s",
            file_path, expected_sha256, ref.sha256,
        )
        raise RuntimeError(f"测试数据文件 hash 不匹配: {file_path}")

    return ref


def _resolve_file(object_name: str) -> Path | None:
    """通过 storage 层解析文件路径。本地存储直接返回路径，远程下载到临时目录。"""
    if hasattr(_storage, "get_path"):
        return _storage.get_path(object_name)

    # S3/MinIO 远程存储：下载到本地临时目录
    import tempfile

    tmp_root = Path(tempfile.gettempdir()) / "acoj-worker-testdata"
    tmp_root.mkdir(parents=True, exist_ok=True)
    _downloaded_dirs.append(tmp_root)

    local_file = tmp_root / object_name
    if not local_file.exists():
        local_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info("从远程存储下载测试文件: %s", object_name)
        content = _storage.download_bytes(object_name)
        local_file.write_bytes(content)

    return local_file


def cleanup_remote_files():
    """清理从远程存储下载的临时文件。在每次 process() 完成后调用。"""
    for d in _downloaded_dirs:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    _downloaded_dirs.clear()
