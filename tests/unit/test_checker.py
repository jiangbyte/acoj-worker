"""输出比对单元测试 — check_output 纯函数。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.modules.judge.checker import check_output


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
