"""输出比对单元测试 — check_output / outputs_match。"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.modules.judge.checker import check_output, outputs_match


def test_exact_match():
    assert check_output("hello world", "hello world") is True


def test_trailing_whitespace_ignored():
    assert check_output("hello world  \n", "hello world") is True


def test_leading_whitespace_ignored():
    assert check_output("  hello world", "hello world") is True


def test_mid_whitespace_not_ignored():
    assert check_output("hello  world", "hello world") is False


def test_expected_none():
    """expected=None 视为全匹配（SPJ 场景 — 实际输出由 checker 评判）。"""
    assert check_output("anything", None) is True


def test_empty_both():
    assert check_output("", "") is True


def test_empty_vs_whitespace():
    """空串和纯空白串 strip 后相等。"""
    assert check_output("", "   \n") is True


def test_unicode_content():
    assert check_output("你好 🌍", "你好 🌍") is True
    assert check_output("你好", "你好世界") is False


class _Ref:
    def __init__(self, *, path: str = "", data=None, preview_text: str = ""):
        self.path = path
        self.data = data
        self.preview_text = preview_text


def test_outputs_match_inline():
    assert outputs_match(_Ref(data="3\n"), _Ref(data="3\n")) is True
    assert outputs_match(_Ref(data="3\n"), _Ref(data="4\n")) is False


def test_outputs_match_ignores_preview_only_trap():
    """preview 相同但全文不同 → WA（必须读 path 全量）。"""
    with tempfile.TemporaryDirectory() as tmp:
        actual = Path(tmp) / "actual.txt"
        expected = Path(tmp) / "expected.txt"
        head = "x" * 5000
        actual.write_text(head + "A", encoding="utf-8")
        expected.write_text(head + "B", encoding="utf-8")
        # 伪造误导性 preview（仅看 preview 会误判 AC）
        actual_ref = _Ref(path=str(actual), preview_text=head[:100])
        expected_ref = _Ref(path=str(expected), preview_text=head[:100])
        assert outputs_match(actual_ref, expected_ref) is False


def test_outputs_match_large_tail_diff():
    with tempfile.TemporaryDirectory() as tmp:
        actual = Path(tmp) / "a.txt"
        expected = Path(tmp) / "e.txt"
        body = ("line\n" * 2000) + "END-A\n"
        body_e = ("line\n" * 2000) + "END-B\n"
        actual.write_text(body, encoding="utf-8")
        expected.write_text(body_e, encoding="utf-8")
        assert outputs_match(_Ref(path=str(actual)), _Ref(path=str(expected))) is False
        expected.write_text(body, encoding="utf-8")
        assert outputs_match(_Ref(path=str(actual)), _Ref(path=str(expected))) is True


def test_outputs_match_expected_none():
    assert outputs_match(_Ref(data="anything"), None) is True
