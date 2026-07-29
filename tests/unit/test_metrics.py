"""Unit tests for run/compile metric aggregation."""

from acoj_sandbox import Status

from app.modules.judge.metrics import (
    compile_metrics_from_process,
    reported_run_time_ms,
    run_metrics_from_cases,
)


def test_run_metrics_sum_time_max_memory():
    cases = [
        {"case_no": 1, "result": "AC", "time_ms": 10, "memory_kb": 4000},
        {"case_no": 2, "result": "AC", "time_ms": 25, "memory_kb": 8000},
        {"case_no": 3, "result": "SKIPPED", "time_ms": 0, "memory_kb": 0},
    ]
    time_ms, memory_kb = run_metrics_from_cases(cases)
    assert time_ms == 35
    assert memory_kb == 8000


def test_run_metrics_empty():
    assert run_metrics_from_cases([]) == (0, 0)


def test_compile_metrics_from_process():
    class _P:
        cpu_time_ms = 420
        memory_bytes = 64 * 1024 * 1024

    assert compile_metrics_from_process(_P()) == (420, 65536)
    assert compile_metrics_from_process(None) == (0, 0)


def test_reported_run_time_ac_uses_cpu():
    class _R:
        status = Status.AC
        cpu_time_ms = 12
        real_time_ms = 40
        message = ""

    assert reported_run_time_ms(_R()) == 12


def test_reported_run_time_tle_uses_max_cpu_real():
    class _R:
        status = Status.TLE
        cpu_time_ms = 50
        real_time_ms = 1500
        message = "time limit exceeded"

    assert reported_run_time_ms(_R()) == 1500
