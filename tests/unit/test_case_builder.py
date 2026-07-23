"""测点构建单元测试 — build_judge_limits / build_judge_cases / get_expected_text。

需要 mock DataRef.from_data 返回简单对象以避免 sandbox C 扩展的意外副作用。
"""

import sys
import os
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.modules.judge.case_builder import build_judge_limits, get_expected_text


# ── build_judge_limits ──


def test_limits_from_case():
    """tc 有 time_limit_ms → 用 tc 的值。"""
    limits = build_judge_limits(
        {"time_limit_ms": 500, "memory_limit_kb": 65536},
        {"time_limit_ms": 2000, "memory_limit_kb": 262144},
    )
    assert limits.cpu_time_ms == 500
    assert limits.memory_bytes == 65536 * 1024


def test_limits_from_problem():
    """tc 无 time_limit_ms → fallback 到 problem。"""
    limits = build_judge_limits(
        {},
        {"time_limit_ms": 2000, "memory_limit_kb": 262144},
    )
    assert limits.cpu_time_ms == 2000
    assert limits.memory_bytes == 262144 * 1024


def test_real_time_3x_cpu():
    """real_time_ms = cpu_time_ms * 3。"""
    limits = build_judge_limits(
        {"time_limit_ms": 1000, "memory_limit_kb": 65536},
        {"time_limit_ms": 2000, "memory_limit_kb": 262144},
    )
    assert limits.real_time_ms == 3000


def test_memory_bytes_conversion():
    """memory_limit_kb → memory_bytes（*1024）。"""
    limits = build_judge_limits(
        {"time_limit_ms": 1000, "memory_limit_kb": 128},
        {},
    )
    assert limits.memory_bytes == 128 * 1024


# ── build_judge_cases（需要 mock DataRef）──


def test_multiple_cases():
    """多测点 → 多个 JudgeCase。"""

    class FakeDataRef:
        data = ""
        preview_text = ""
        sha256 = ""

        @staticmethod
        def from_data(d):
            r = FakeDataRef()
            r.data = d
            r.preview_text = d
            return r

    with patch("app.modules.judge.case_builder.resolve_input_ref", return_value=FakeDataRef.from_data("")), \
         patch("app.modules.judge.case_builder.resolve_output_ref", return_value=FakeDataRef.from_data("")):
        from app.modules.judge.case_builder import build_judge_cases

        cases = build_judge_cases(
            [
                {"case_no": 1, "points": 50.0, "time_limit_ms": 1000, "memory_limit_kb": 65536},
                {"case_no": 2, "points": 50.0, "time_limit_ms": 1000, "memory_limit_kb": 65536},
            ],
            {"time_limit_ms": 2000, "memory_limit_kb": 262144},
        )
        assert len(cases) == 2
        assert cases[0].case_id == "1"
        assert cases[1].case_id == "2"


# ── get_expected_text ──


def test_get_expected_text_from_result():
    """case_result.expected_output.preview_text 非空 → 用它。"""
    class FakeExpected:
        preview_text = "expected from sandbox"
    class FakeCaseResult:
        expected_output = FakeExpected()

    text = get_expected_text(FakeCaseResult(), {"output_inline": "expected from meta"})
    assert text == "expected from sandbox"


def test_get_expected_text_from_meta():
    """expected_output=None → fallback 到 tc_meta output_inline。"""
    class FakeCaseResult:
        expected_output = None

    text = get_expected_text(FakeCaseResult(), {"output_inline": "expected from meta"})
    assert text == "expected from meta"


def test_get_expected_text_fallback_empty():
    """两个都没有 → 空字符串。"""
    class FakeCaseResult:
        expected_output = None

    text = get_expected_text(FakeCaseResult(), {})
    assert text == ""
