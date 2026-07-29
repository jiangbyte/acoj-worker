"""测试用例构建：从 MQ payload 的 test_cases 生成 sandbox JudgeCase 列表。"""

from acoj_sandbox import JudgeCase, JudgeLimits

from app.modules.judge.data_loader import resolve_input_ref, resolve_output_ref

# 默认输出上限 8MiB（OJ 常见）；可用 problem/tc 的 output_limit_bytes 覆盖
_DEFAULT_OUTPUT_BYTES = 8 * 1024 * 1024


def build_judge_limits(tc: dict, problem: dict) -> JudgeLimits:
    """从测试用例或题目配置构建 JudgeLimits。"""
    cpu_ms = tc.get("time_limit_ms") or problem["time_limit_ms"]
    output_bytes = (
        tc.get("output_limit_bytes")
        or problem.get("output_limit_bytes")
        or _DEFAULT_OUTPUT_BYTES
    )
    return JudgeLimits(
        cpu_time_ms=cpu_ms,
        real_time_ms=cpu_ms * 3,
        memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
        processes=256,
        output_bytes=int(output_bytes),
    )


def build_judge_cases(test_cases_data: list[dict], problem: dict) -> list[JudgeCase]:
    """构建 sandbox 可处理的 JudgeCase 列表。"""
    cases: list[JudgeCase] = []
    for tc in test_cases_data:
        cases.append(
            JudgeCase(
                case_id=str(tc["case_no"]),
                input=resolve_input_ref(tc),
                expected_output=resolve_output_ref(tc),
                limits=build_judge_limits(tc, problem),
            )
        )
    return cases
