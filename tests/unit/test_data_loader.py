"""data_loader：FILE 缺失必须硬失败，不得退回空 inline。"""

import pytest

from app.modules.judge import data_loader


def test_missing_input_file_raises(monkeypatch):
    monkeypatch.setattr(data_loader, "_resolve_file", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError, match="输入文件不存在"):
        data_loader.resolve_input_ref({"input_file": "missing/1.in", "input_sha256": "ab"})


def test_missing_output_file_raises(monkeypatch):
    monkeypatch.setattr(data_loader, "_resolve_file", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError, match="输出文件不存在"):
        data_loader.resolve_output_ref({"output_file": "missing/1.out", "output_sha256": "cd"})


def test_inline_input_still_works():
    ref = data_loader.resolve_input_ref({"input_inline": "hi\n"})
    assert ref.data == "hi\n" or (hasattr(ref, "data") and ref.data in ("hi\n", b"hi\n"))
