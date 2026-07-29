"""Pydantic Schema 校验单元测试 — JudgePayload / JudgeResultOut / CaseResult。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from pydantic import ValidationError
from app.modules.judge.schemas import (
    JudgePayload,
    JudgeResultOut,
    CaseResult,
    ProblemConfig,
    TestCaseData,
    LanguageConfigIn,
)


# ── JudgePayload ──


def test_valid_minimal_payload():
    """最小合法 payload。"""
    p = JudgePayload(
        submission_id="test-1",
        problem={"code": "p1", "time_limit_ms": 1000, "memory_limit_kb": 65536},
    )
    assert p.submission_id == "test-1"
    assert p.judge_mode == "STANDARD"
    assert p.test_cases == []


def test_valid_full_payload():
    """完整 STANDARD payload。"""
    p = JudgePayload(
        submission_id="test-2",
        judge_mode="STANDARD",
        problem=ProblemConfig(code="p2", time_limit_ms=2000, memory_limit_kb=262144),
        language=LanguageConfigIn(key="cpp17"),
        source='#include <iostream>\nint main() {}\n',
        test_cases=[TestCaseData(case_no=1, points=100.0, input_inline="", output_inline="ok")],
    )
    assert p.judge_mode == "STANDARD"
    assert len(p.test_cases) == 1


def test_valid_spj_payload():
    """SPJ payload 含 spj 字段。"""
    p = JudgePayload(
        submission_id="test-3",
        judge_mode="SPECIAL_JUDGE",
        problem={"code": "p3", "time_limit_ms": 2000, "memory_limit_kb": 262144},
        source="int main() { return 0; }",
        spj={"language": {"key": "cpp17"}, "source": "#include <iostream>"},
    )
    assert p.spj is not None
    assert p.spj["language"]["key"] == "cpp17"


def test_valid_interactive_payload():
    """INTERACTIVE payload 含 interactor 字段。"""
    p = JudgePayload(
        submission_id="test-4",
        judge_mode="INTERACTIVE",
        problem={"code": "p4", "time_limit_ms": 2000, "memory_limit_kb": 262144},
        source="int main() { return 0; }",
        interactor={"language": {"key": "cpp17"}, "source": "#include <iostream>"},
    )
    assert p.interactor is not None


def test_invalid_missing_submission_id():
    """缺 submission_id → ValidationError。"""
    try:
        JudgePayload(problem={"code": "p", "time_limit_ms": 1000, "memory_limit_kb": 65536})
        assert False, "应抛 ValidationError"
    except ValidationError:
        pass


def test_valid_empty_test_cases():
    """test_cases=[] 合法（由业务层处理为 FAILED）。"""
    p = JudgePayload(
        submission_id="test-5",
        problem={"code": "p", "time_limit_ms": 1000, "memory_limit_kb": 65536},
        test_cases=[],
    )
    assert p.test_cases == []


def test_negative_points_allowed():
    """points 无 ge=0 约束，负分不触发 ValidationError。"""
    c = TestCaseData(case_no=1, points=-1.0)
    assert c.points == -1.0


def test_valid_any_judge_mode():
    """judge_mode 可以为任意字符串（由 registry 兜底）。"""
    p = JudgePayload(
        submission_id="test-6",
        judge_mode="UNKNOWN_MODE",
        problem={"code": "p", "time_limit_ms": 1000, "memory_limit_kb": 65536},
    )
    assert p.judge_mode == "UNKNOWN_MODE"


# ── CaseResult ──


def test_case_result_defaults():
    """CaseResult 默认值：result=IE, time=0, mem=0, points=0。"""
    c = CaseResult(case_no=1)
    assert c.result == "IE"
    assert c.time_ms == 0
    assert c.memory_kb == 0
    assert c.points == 0.0


def test_case_result_serialization():
    """CaseResult 序列化为 dict。"""
    c = CaseResult(case_no=1, result="AC", time_ms=42, memory_kb=4096, points=100.0)
    d = c.model_dump()
    assert d["case_no"] == 1
    assert d["result"] == "AC"
    assert d["time_ms"] == 42


# ── JudgeResultOut ──


def test_judge_result_out_defaults():
    """JudgeResultOut 默认值：status=COMPLETED, result=None, score=0.0。"""
    r = JudgeResultOut(submission_id="test-7")
    assert r.status == "COMPLETED"
    assert r.result is None
    assert r.score == 0.0
    assert r.time_ms == 0
    assert r.memory_kb == 0
    assert r.compile_time_ms == 0
    assert r.compile_memory_kb == 0
    assert r.cases == []


def test_judge_result_out_model_dump():
    """Celery 返回值协议体字段完整。"""
    r = JudgeResultOut(
        submission_id="test-8",
        result="AC",
        score=100.0,
        time_ms=42,
        memory_kb=4096,
        compile_time_ms=300,
        compile_memory_kb=65536,
    )
    d = r.model_dump()
    assert d["submission_id"] == "test-8"
    assert d["result"] == "AC"
    assert d["score"] == 100.0
    assert d["time_ms"] == 42
    assert d["compile_time_ms"] == 300
    assert "cases" in d
