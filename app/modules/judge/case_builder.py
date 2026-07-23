"""测试用例构建：从 MQ payload 的 test_cases 生成 sandbox JudgeCase 列表。"""

from acoj_sandbox import JudgeCase, JudgeLimits

from app.modules.judge.data_loader import resolve_input_ref, resolve_output_ref


def build_judge_limits(tc: dict, problem: dict) -> JudgeLimits:
    """从测试用例或题目配置构建 JudgeLimits。"""
    return JudgeLimits(
        cpu_time_ms=tc.get("time_limit_ms") or problem["time_limit_ms"],
        real_time_ms=(tc.get("time_limit_ms") or problem["time_limit_ms"]) * 3,
        memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
        processes=256,
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


def get_expected_text(case_result, tc_meta: dict) -> str:
    """从 sandbox 结果或 test_case 元数据中获取预期输出文本。"""
    expected_ref = case_result.expected_output
    if expected_ref is not None and expected_ref.preview_text:
        return expected_ref.preview_text
    return tc_meta.get("output_inline") or ""
