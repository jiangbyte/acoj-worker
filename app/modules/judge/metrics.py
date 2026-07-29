"""判题结果资源字段聚合。

顶层 time_ms / memory_kb：仅用户程序**运行**测例（OJ 成绩语义）。
编译阶段单独放在 compile_time_ms / compile_memory_kb。
"""

from __future__ import annotations

from acoj_sandbox import Status


def run_metrics_from_cases(cases: list[dict]) -> tuple[int, int]:
    """从测例结果汇总运行用时/内存。

    - time_ms：各测例报告时间之和（SKIPPED 一般为 0）
    - memory_kb：各测例峰值 RSS 的最大值
    """
    time_ms = sum(int(c.get("time_ms") or 0) for c in cases)
    memory_kb = max((int(c.get("memory_kb") or 0) for c in cases), default=0)
    return time_ms, memory_kb


def compile_metrics_from_process(compile_result) -> tuple[int, int]:
    """从 sandbox 编译 ProcessResult 取编译用时/内存。"""
    if compile_result is None:
        return 0, 0
    time_ms = int(getattr(compile_result, "cpu_time_ms", 0) or 0)
    memory_bytes = int(getattr(compile_result, "memory_bytes", 0) or 0)
    return time_ms, memory_bytes // 1024


def reported_run_time_ms(run) -> int:
    """测例对外报告用时。

    普通 AC/RE/…：CPU 时间。
    TLE：取 max(cpu, real)，避免因 wall 限时杀掉时 CPU 很小、看起来「未到时限却 TLE」。
    """
    if run is None:
        return 0
    cpu = int(getattr(run, "cpu_time_ms", 0) or 0)
    real = int(getattr(run, "real_time_ms", 0) or 0)
    status = getattr(run, "status", None)
    if status == Status.TLE or getattr(run, "message", "") == "time limit exceeded":
        return max(cpu, real)
    return cpu
