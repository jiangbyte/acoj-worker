"""将 sandbox 状态码映射为 OJ 判题结果。"""

from acoj_sandbox import Status

# sandbox 只报告执行状态，不包含 WA（WA 由输出比对确定）
SANDBOX_TO_OJ_RESULT: dict[Status, str] = {
    Status.AC: "AC",
    Status.CE: "CE",
    Status.RE: "RE",
    Status.TLE: "TLE",
    Status.MLE: "MLE",
    Status.OLE: "OLE",
    Status.SE: "SE",
    Status.IE: "IE",
}


def to_oj_result(status: Status) -> str:
    return SANDBOX_TO_OJ_RESULT.get(status, "IE")


def compute_overall_result(has_compile_error: bool, case_results: list[dict]) -> str:
    if has_compile_error:
        return "CE"
    for case in case_results:
        if case["result"] not in ("AC", "SKIPPED"):
            return case["result"]
    return "AC"


def compute_score(has_compile_error: bool, case_results: list[dict]) -> float:
    if has_compile_error:
        return 0.0
    total = 0.0
    for case in case_results:
        if case["result"] == "AC":
            total += case.get("points", 0.0)
    return total
