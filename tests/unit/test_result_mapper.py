"""结果映射器单元测试 — to_oj_result / compute_overall_result / compute_score。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from acoj_sandbox import Status
from app.modules.judge.result_mapper import (
    to_oj_result,
    compute_overall_result,
    compute_score,
    SANDBOX_TO_OJ_RESULT,
)


# ── to_oj_result ──


def test_all_sandbox_statuses_mapped():
    """所有 8 个 Status 值均有对应 OJ 字符串。"""
    assert SANDBOX_TO_OJ_RESULT[Status.AC] == "AC"
    assert SANDBOX_TO_OJ_RESULT[Status.CE] == "CE"
    assert SANDBOX_TO_OJ_RESULT[Status.RE] == "RE"
    assert SANDBOX_TO_OJ_RESULT[Status.TLE] == "TLE"
    assert SANDBOX_TO_OJ_RESULT[Status.MLE] == "MLE"
    assert SANDBOX_TO_OJ_RESULT[Status.OLE] == "OLE"
    assert SANDBOX_TO_OJ_RESULT[Status.SE] == "SE"
    assert SANDBOX_TO_OJ_RESULT[Status.IE] == "IE"


def test_to_oj_result_unknown():
    """未知 Status 默认返回 IE（传入不存在的值）。"""
    assert to_oj_result("INVALID_STATUS") == "IE"


# ── compute_overall_result ──


def test_compute_overall_ac():
    cases = [{"result": "AC"}, {"result": "AC"}]
    assert compute_overall_result(False, cases) == "AC"


def test_compute_overall_with_skipped():
    """SKIPPED 不算失败，整体仍为 AC。"""
    cases = [{"result": "AC"}, {"result": "SKIPPED"}]
    assert compute_overall_result(False, cases) == "AC"


def test_compute_overall_first_non_ac():
    """取第一个非 AC/SKIPPED 的结果。"""
    cases = [{"result": "WA"}, {"result": "AC"}, {"result": "AC"}]
    assert compute_overall_result(False, cases) == "WA"


def test_compute_overall_ce():
    """编译错误 → CE 优先于所有 case 结果。"""
    cases = [{"result": "AC"}]
    assert compute_overall_result(True, cases) == "CE"


# ── compute_score ──


def test_compute_score_all_ac():
    cases = [{"result": "AC", "points": 33.33}, {"result": "AC", "points": 66.67}]
    assert abs(compute_score(False, cases) - 100.0) < 0.01


def test_compute_score_partial():
    cases = [
        {"result": "AC", "points": 50.0},
        {"result": "WA", "points": 50.0},
    ]
    assert abs(compute_score(False, cases) - 50.0) < 0.01


def test_compute_score_ce():
    cases = [{"result": "AC", "points": 100.0}]
    assert compute_score(True, cases) == 0.0
