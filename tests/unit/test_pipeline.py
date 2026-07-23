"""Judge Pipeline 集成单元测试 — mock SandboxClient 测试完整 judge() 链路。

通过 patch('app.modules.judge.modes.standard.SandboxClient') 等，
零外部依赖，测试 orchestrator 和各模式的分支逻辑。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import patch, MagicMock, PropertyMock

from acoj_sandbox import Status

from app.modules.judge.orchestrator import judge


def _status_result_mock(status: Status):
    """构造 mock BatchResult/Package 的 status 字段。"""
    m = MagicMock()
    m.status = status
    return m


def _make_mock_batch_result(compile_status=Status.AC, case_statuses=None):
    """构造 mock run_cases 的 BatchResult。"""
    batch = MagicMock()
    batch.compile = _status_result_mock(compile_status)
    batch.total_cpu_time_ms = 10
    batch.peak_memory_bytes = 4096
    batch.message = ""
    if compile_status != Status.AC:
        batch.message = "compile error msg"

    cases = []
    for i, st in enumerate(case_statuses or [Status.AC]):
        case = MagicMock()
        case.status = st
        case.result.run.cpu_time_ms = 5
        case.result.run.memory_bytes = 2048
        case.actual_output.preview_text = f"output{i}"
        case.stderr.preview_text = ""
        if st == Status.AC:
            case.expected_output = MagicMock()
            case.expected_output.preview_text = f"output{i}"
        else:
            case.expected_output = None
        cases.append(case)
    batch.cases = cases
    return batch


def _make_mock_program(compiled=True, compile_status=Status.AC):
    """mock prepare_source 返回的编译后程序。"""
    prog = MagicMock()
    prog.compiled = compiled
    prog.compile.status = compile_status
    prog.compile.message = ""
    prog.run.return_value = _make_mock_run_result(Status.AC, "user output")
    return prog


def _make_mock_run_result(status=Status.AC, stdout_text="output"):
    rr = MagicMock()
    rr.status = status
    rr.stdout = stdout_text
    rr.run.cpu_time_ms = 5
    rr.run.memory_bytes = 2048
    rr.stdout_path = "/tmp/stdout"
    return rr


# ── STANDARD ──


def test_standard_ac_flow():
    """STANDARD 模式 mock → 返回 AC。"""
    mock_client = MagicMock()
    mock_client.run_cases.return_value = _make_mock_batch_result(Status.AC, [Status.AC])
    mock_client.close.return_value = None

    with patch("app.modules.judge.modes.standard.SandboxClient", return_value=mock_client):
        result = judge({
            "submission_id": "ut-std-ac",
            "judge_mode": "STANDARD",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": "output0"}],
        })

    assert result["result"] == "AC"
    assert abs(result["score"] - 100.0) < 0.01


def test_standard_wa_flow():
    """输出不匹配 → WA。"""
    mock_client = MagicMock()
    mock_client.run_cases.return_value = _make_mock_batch_result(Status.AC, [Status.AC])
    # 修改预期输出为不匹配的值
    mock_client.run_cases.return_value.cases[0].expected_output.preview_text = "expected"
    mock_client.run_cases.return_value.cases[0].actual_output.preview_text = "wrong"

    with patch("app.modules.judge.modes.standard.SandboxClient", return_value=mock_client):
        result = judge({
            "submission_id": "ut-std-wa",
            "judge_mode": "STANDARD",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": "expected"}],
        })

    assert result["result"] == "WA"


def test_standard_ce_flow():
    """编译错 → CE。"""
    mock_client = MagicMock()
    mock_client.run_cases.return_value = _make_mock_batch_result(Status.CE, [Status.AC])

    with patch("app.modules.judge.modes.standard.SandboxClient", return_value=mock_client):
        result = judge({
            "submission_id": "ut-std-ce",
            "judge_mode": "STANDARD",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "broken code",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": ""}],
        })

    assert result["result"] == "CE"
    assert result["score"] == 0.0


def test_standard_tle_flow():
    """超时 → TLE。"""
    mock_client = MagicMock()
    mock_client.run_cases.return_value = _make_mock_batch_result(Status.AC, [Status.TLE])

    with patch("app.modules.judge.modes.standard.SandboxClient", return_value=mock_client):
        result = judge({
            "submission_id": "ut-std-tle",
            "judge_mode": "STANDARD",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { while(1) {} }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": ""}],
        })

    assert result["result"] == "TLE"


# ── SPJ ──


def test_spj_ac_flow():
    """SPJ checker accepted=True → AC。"""
    mock_client = MagicMock()
    mock_prog = _make_mock_program(compiled=True)
    mock_client.prepare_source.return_value = mock_prog
    mock_prog.run.return_value = _make_mock_run_result(Status.AC, "ACCEPT")

    mock_checker_client = MagicMock()
    mock_checker_prog = _make_mock_program(compiled=True)
    mock_checker_client.prepare_source.return_value = mock_checker_prog

    spj_result = MagicMock()
    spj_result.accepted = True
    mock_client.run_testlib_checker.return_value = spj_result

    # Mock DataRef.from_path to avoid file I/O
    fake_ref = MagicMock()
    fake_ref.data = ""
    fake_ref.preview_text = "ACCEPT"

    with patch("app.modules.judge.modes.spj.SandboxClient",
               side_effect=[mock_client, mock_checker_client]), \
         patch("app.modules.judge.modes.spj.DataRef.from_path", return_value=fake_ref):
        result = judge({
            "submission_id": "ut-spj-ac",
            "judge_mode": "SPECIAL_JUDGE",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": None}],
            "spj": {"language": {"key": "cpp17"}, "source": "int main() { return 0; }"},
        })

    assert result["result"] == "AC"
    assert abs(result["score"] - 100.0) < 0.01


def test_spj_wa_flow():
    """SPJ checker accepted=False → WA。"""
    mock_client = MagicMock()
    mock_prog = _make_mock_program(compiled=True)
    mock_client.prepare_source.return_value = mock_prog
    mock_prog.run.return_value = _make_mock_run_result(Status.AC, "WRONG")

    mock_checker_client = MagicMock()
    mock_checker_prog = _make_mock_program(compiled=True)
    mock_checker_client.prepare_source.return_value = mock_checker_prog

    spj_result = MagicMock()
    spj_result.accepted = False
    mock_client.run_testlib_checker.return_value = spj_result

    fake_ref = MagicMock()
    fake_ref.data = ""
    fake_ref.preview_text = "WRONG"

    with patch("app.modules.judge.modes.spj.SandboxClient",
               side_effect=[mock_client, mock_checker_client]), \
         patch("app.modules.judge.modes.spj.DataRef.from_path", return_value=fake_ref):
        result = judge({
            "submission_id": "ut-spj-wa",
            "judge_mode": "SPECIAL_JUDGE",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": None}],
            "spj": {"language": {"key": "cpp17"}, "source": "int main() { return 0; }"},
        })

    assert result["result"] == "WA"


# ── INTERACTIVE ──


def test_interactive_ac_flow():
    """INTERACTIVE user+interactor both AC → AC。"""
    mock_user_client = MagicMock()
    mock_user_prog = _make_mock_program(compiled=True)
    mock_user_client.prepare_source.return_value = mock_user_prog
    mock_user_prog.run_with_paths.return_value = _make_mock_run_result(Status.AC)

    mock_int_client = MagicMock()
    mock_int_prog = _make_mock_program(compiled=True)
    mock_int_client.prepare_source.return_value = mock_int_prog
    mock_int_prog.run_with_paths.return_value = _make_mock_run_result(Status.AC)
    mock_int_prog.run_with_paths.return_value.run.exit_code = 0

    def _user_client_side_effect(**kw):
        return mock_user_client
    def _int_client_side_effect(**kw):
        return mock_int_client

    # interactive 模式中 user_client 和 interactor_client 是独立创建的
    clients_iter = iter([mock_user_client, mock_int_client])
    real_client = MagicMock()
    real_client.prepare_source.side_effect = [mock_user_prog, mock_int_prog]

    def client_factory(**kw):
        return next(clients_iter)

    from unittest.mock import call
    # interactive 模式调用 2 次 SandboxClient（user + interactor）
    with patch("app.modules.judge.modes.interactive.SandboxClient",
               side_effect=[mock_user_client, mock_int_client]):
        result = judge({
            "submission_id": "ut-int-ac",
            "judge_mode": "INTERACTIVE",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": None}],
            "interactor": {
                "language": {"key": "cpp17"},
                "source": "int main() { return 0; }",
                "time_limit_ms": 4000, "memory_limit_kb": 262144,
            },
        })

    assert result["result"] == "AC"


# ── Orchestrator ──


def test_orchestrator_unknown_mode_fallback():
    """未知 judge_mode → fallback STANDARD。"""
    mock_client = MagicMock()
    mock_client.run_cases.return_value = _make_mock_batch_result(Status.AC, [Status.AC])
    mock_client.close.return_value = None

    with patch("app.modules.judge.modes.standard.SandboxClient", return_value=mock_client):
        result = judge({
            "submission_id": "ut-unknown",
            "judge_mode": "UNKNOWN_MODE_THAT_DOES_NOT_EXIST",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": "output0"}],
        })

    # 未抛异常说明 fallback 成功
    assert result["result"] in ("AC", "TLE", "WA")


def test_orchestrator_exception_results_failed():
    """mode.judge() 抛异常 → 返回 FAILED。"""
    with patch("app.modules.judge.modes.standard.StandardMode.judge",
               side_effect=RuntimeError("模拟异常")):
        result = judge({
            "submission_id": "ut-exc",
            "judge_mode": "STANDARD",
            "problem": {"code": "p", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0},
            "language": {"key": "cpp17"},
            "source": "int main() { return 0; }",
            "test_cases": [{"case_no": 1, "points": 100.0, "input_inline": "", "output_inline": ""}],
        })

    assert result["status"] == "FAILED"
    assert result["result"] is None
    assert "模拟异常" in result.get("error", "")
