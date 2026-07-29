"""计分逻辑：IOI 批次聚合、通用错误结果构造。

IOI 批次规则：
  - 同 batch_no 的用例必须全部 AC 才给分
  - batch_depends 声明依赖：依赖批次失败则该批次标记 SKIPPED
  - 无 batch_no 的用例独立计分
  - 非 batch 模式（ACM/OI）不经过此处
"""

from collections import defaultdict


def _compute_batch_ac_status(
    raw_case_results: list[dict],
    test_cases_data: list[dict],
) -> dict[int | None, bool]:
    """计算每个 batch 的 AC 状态（批次内全部 AC 才为 True）。"""
    batch_ac: dict[int | None, bool] = {}
    for tc, cr in zip(test_cases_data, raw_case_results):
        bn = tc.get("batch_no")
        if bn is not None:
            prev = batch_ac.get(bn, True)
            batch_ac[bn] = prev and cr["result"] == "AC"
    return batch_ac


def _apply_batch_dependencies(
    raw_case_results: list[dict],
    test_cases_data: list[dict],
    batch_ac: dict[int | None, bool],
) -> None:
    """根据 batch_depends 依赖关系标记 SKIPPED。"""
    for tc, cr in zip(test_cases_data, raw_case_results):
        bn = tc.get("batch_no")
        if bn is not None:
            deps = tc.get("batch_depends") or tc.get("batch_dependencies") or []
            for dep in deps:
                if dep in batch_ac and not batch_ac[dep]:
                    cr["result"] = "SKIPPED"
                    cr["points"] = 0.0


def aggregate_batches(
    raw_case_results: list[dict],
    test_cases_data: list[dict],
) -> tuple[list[dict], float]:
    """IOI 批次计分：同 batch 全过才给分，依赖失败跳过。

    Returns:
        (case_results, total_score)
    """
    # Phase 1: 计算初始 batch AC 状态
    batch_ac = _compute_batch_ac_status(raw_case_results, test_cases_data)

    # Phase 2: 应用 batch 依赖（失败的依赖导致 SKIPPED）
    _apply_batch_dependencies(raw_case_results, test_cases_data, batch_ac)

    # Phase 3: 重新计算（依赖可能导致批次状态变化）
    batch_ac = _compute_batch_ac_status(raw_case_results, test_cases_data)

    # Phase 4: 按 batch 分组并计分
    batches: dict[int | None, list[dict]] = defaultdict(list)
    batch_order: list[int | None] = []
    seen: set[int | None] = set()
    for cr, tc in zip(raw_case_results, test_cases_data):
        bn = tc.get("batch_no")
        if bn not in seen:
            seen.add(bn)
            batch_order.append(bn)
        batches[bn].append(cr)

    case_results: list[dict] = []
    total_score = 0.0

    for bn in batch_order:
        batch_cases = batches[bn]
        if bn is None:
            for c in batch_cases:
                case_results.append(c)
                if c["result"] == "AC":
                    total_score += c["points"]
        else:
            if batch_ac.get(bn, True):
                batch_points = sum(c["points"] for c in batch_cases)
                for c in batch_cases:
                    case_results.append(dict(c))
                total_score += batch_points
            else:
                for c in batch_cases:
                    c_adj = dict(c)
                    c_adj["points"] = 0.0
                    case_results.append(c_adj)

    return case_results, total_score


def error_verdict(submission_id: str, msg: str) -> dict:
    """构造快速失败结果。"""
    return {
        "submission_id": submission_id,
        "status": "FAILED",
        "result": None,
        "score": 0.0,
        "time_ms": 0,
        "memory_kb": 0,
        "compile_time_ms": 0,
        "compile_memory_kb": 0,
        "compile_output": msg,
        "compile_error": False,
        "cases": [],
        "error": msg,
    }
