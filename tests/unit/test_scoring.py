"""计分逻辑单元测试 — aggregate_batches / error_verdict 纯函数。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.modules.judge.scoring import aggregate_batches, error_verdict


def test_no_batch_independent():
    """无 batch_no 的用例独立计分。"""
    cases = [
        {"case_no": 1, "result": "AC", "points": 50.0},
        {"case_no": 2, "result": "AC", "points": 50.0},
    ]
    metas = [{"points": 50.0}, {"points": 50.0}]
    results, score = aggregate_batches(cases, metas)
    assert abs(score - 100.0) < 0.01
    assert all(c["result"] == "AC" for c in results)


def test_single_batch_all_ac():
    """同 batch 全部 AC → 全给分。"""
    cases = [
        {"case_no": 1, "result": "AC", "points": 25.0},
        {"case_no": 2, "result": "AC", "points": 25.0},
    ]
    metas = [
        {"points": 25.0, "batch_no": 1},
        {"points": 25.0, "batch_no": 1},
    ]
    results, score = aggregate_batches(cases, metas)
    assert abs(score - 50.0) < 0.01


def test_single_batch_one_wa():
    """同 batch 一个 WA → 整批 0 分。"""
    cases = [
        {"case_no": 1, "result": "AC", "points": 25.0},
        {"case_no": 2, "result": "WA", "points": 25.0},
    ]
    metas = [
        {"points": 25.0, "batch_no": 1},
        {"points": 25.0, "batch_no": 1},
    ]
    results, score = aggregate_batches(cases, metas)
    assert abs(score - 0.0) < 0.01
    assert results[1]["points"] == 0.0


def test_batch_depends_fail():
    """batch1 失败 → batch2 全部 SKIPPED。"""
    cases = [
        {"case_no": 1, "result": "WA", "points": 25.0},
        {"case_no": 2, "result": "AC", "points": 25.0},
        {"case_no": 3, "result": "AC", "points": 25.0},
    ]
    metas = [
        {"points": 25.0, "batch_no": 1},
        {"points": 25.0, "batch_no": 2, "batch_depends": [1]},
        {"points": 25.0, "batch_no": 2, "batch_depends": [1]},
    ]
    results, score = aggregate_batches(cases, metas)
    assert results[1]["result"] == "SKIPPED"
    assert results[2]["result"] == "SKIPPED"
    assert abs(score - 0.0) < 0.01


def test_batch_depends_success():
    """batch1 成功 → batch2 正常计分。"""
    cases = [
        {"case_no": 1, "result": "AC", "points": 25.0},
        {"case_no": 2, "result": "AC", "points": 25.0},
    ]
    metas = [
        {"points": 25.0, "batch_no": 1},
        {"points": 25.0, "batch_no": 2, "batch_depends": [1]},
    ]
    results, score = aggregate_batches(cases, metas)
    assert abs(score - 50.0) < 0.01
    assert all(c["result"] == "AC" for c in results)


def test_mixed_batch_and_none():
    """batch_no 为 None 和 有值 混合 → None 独立计分。"""
    cases = [
        {"case_no": 1, "result": "AC", "points": 33.33},
        {"case_no": 2, "result": "WA", "points": 33.33},
    ]
    metas = [
        {"points": 33.33},
        {"points": 33.33, "batch_no": 1},
    ]
    results, score = aggregate_batches(cases, metas)
    assert abs(score - 33.33) < 0.01


def test_error_verdict():
    """error_verdict 返回 status=FAILED。"""
    r = error_verdict("sid-1", "测试错误")
    assert r["status"] == "FAILED"
    assert r["result"] is None
    assert r["score"] == 0.0
    assert r["submission_id"] == "sid-1"
    assert "测试错误" in r["error"]


def test_batch_depends_chain():
    """batch1→batch2→batch3 依赖链：当前实现只检查直接依赖。
    batch1 失败 → batch2 SKIPPED，但 batch3 仅检查 batch2 的初始 AC 状态（True）→ 保持 AC。
    这是现有代码的行为：_apply_batch_dependencies 不递归传递。
    """
    cases = [
        {"case_no": 1, "result": "WA", "points": 20.0},
        {"case_no": 2, "result": "AC", "points": 20.0},
        {"case_no": 3, "result": "AC", "points": 20.0},
    ]
    metas = [
        {"points": 20.0, "batch_no": 1},
        {"points": 20.0, "batch_no": 2, "batch_depends": [1]},
        {"points": 20.0, "batch_no": 3, "batch_depends": [2]},
    ]
    results, score = aggregate_batches(cases, metas)
    # batch2 SKIPPED（直接依赖 batch1 失败）
    assert results[1]["result"] == "SKIPPED"
    # batch3 检查 batch2 的初始 AC 状态（True），所以保持 AC
    assert results[2]["result"] == "AC"
    # batch1 WA → 0, batch2 SKIPPED → 0, batch3 AC → 20
    assert abs(score - 20.0) < 0.01
