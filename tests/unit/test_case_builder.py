"""测点构建单元测试 — build_judge_limits / build_judge_cases。"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.modules.judge.case_builder import build_judge_limits


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


def test_default_output_bytes():
    limits = build_judge_limits(
        {"time_limit_ms": 1000, "memory_limit_kb": 65536},
        {"time_limit_ms": 2000, "memory_limit_kb": 262144},
    )
    assert limits.output_bytes == 8 * 1024 * 1024


def test_output_limit_bytes_override():
    limits = build_judge_limits(
        {"time_limit_ms": 1000, "memory_limit_kb": 65536, "output_limit_bytes": 2048},
        {"time_limit_ms": 2000, "memory_limit_kb": 262144},
    )
    assert limits.output_bytes == 2048


def test_memory_bytes_conversion():
    """memory_limit_kb → memory_bytes（*1024）。"""
    limits = build_judge_limits(
        {"time_limit_ms": 1000, "memory_limit_kb": 128},
        {},
    )
    assert limits.memory_bytes == 128 * 1024


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

    with (
        patch(
            "app.modules.judge.case_builder.resolve_input_ref",
            return_value=FakeDataRef.from_data(""),
        ),
        patch(
            "app.modules.judge.case_builder.resolve_output_ref",
            return_value=FakeDataRef.from_data(""),
        ),
    ):
        from app.modules.judge.case_builder import build_judge_cases

        cases = build_judge_cases(
            [
                {
                    "case_no": 1,
                    "points": 50.0,
                    "time_limit_ms": 1000,
                    "memory_limit_kb": 65536,
                },
                {
                    "case_no": 2,
                    "points": 50.0,
                    "time_limit_ms": 1000,
                    "memory_limit_kb": 65536,
                },
            ],
            {"time_limit_ms": 2000, "memory_limit_kb": 262144},
        )
        assert len(cases) == 2
        assert cases[0].case_id == "1"
        assert cases[1].case_id == "2"
