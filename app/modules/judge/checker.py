"""输出比对：忽略首尾空白，按全量内容判定（禁止仅用 preview）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def check_output(actual_preview: str, expected_text: str | None) -> bool:
    """比对实际输出和预期输出，返回是否匹配。None 预期视为全匹配。"""
    if expected_text is None:
        return True
    return actual_preview.strip() == expected_text.strip()


def _existing_file(path_value: Any) -> Path | None:
    if not isinstance(path_value, (str, os.PathLike)):
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    return path


def _ref_full_text(ref: Any) -> str | None:
    """从 DataRef 读取全量文本；不用 preview_text。"""
    if ref is None:
        return None
    path = _existing_file(getattr(ref, "path", None))
    if path is not None:
        return path.read_text(encoding="utf-8", errors="replace")
    data = getattr(ref, "data", None)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    if isinstance(data, str):
        return data
    return None


def _paths_match_stripped(path_a: Path, path_b: Path, *, chunk_size: int = 1024 * 1024) -> bool:
    """大文件分块比对，语义等同整文件 strip 后相等。"""
    data_a = path_a.read_bytes()
    data_b = path_b.read_bytes()
    text_a = data_a.decode("utf-8", errors="replace").strip()
    text_b = data_b.decode("utf-8", errors="replace").strip()
    if len(text_a) != len(text_b):
        return False
    ba = text_a.encode("utf-8")
    bb = text_b.encode("utf-8")
    if len(ba) != len(bb):
        return False
    for i in range(0, len(ba), chunk_size):
        if ba[i : i + chunk_size] != bb[i : i + chunk_size]:
            return False
    return True


def outputs_match(actual_ref: Any, expected_ref: Any) -> bool:
    """全量比对 actual / expected DataRef；expected 为 None 视为匹配。"""
    if expected_ref is None:
        return True

    actual_path = _existing_file(getattr(actual_ref, "path", None))
    expected_path = _existing_file(getattr(expected_ref, "path", None))
    if actual_path is not None and expected_path is not None:
        return _paths_match_stripped(actual_path, expected_path)

    expected_text = _ref_full_text(expected_ref)
    if expected_text is None:
        return True
    actual_text = _ref_full_text(actual_ref)
    if actual_text is None:
        actual_text = ""
    return check_output(actual_text, expected_text)
