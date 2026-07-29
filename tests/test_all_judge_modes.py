"""全面判题模式集成测试 — 通过 Celery 发送判题请求。

覆盖 STANDARD(ACM/OI/IOI/CE/RE/TLE/MLE/OLE)、SPECIAL_JUDGE、INTERACTIVE 全部模式。

用法：
    python tests/test_all_judge_modes.py              # 全部
    python tests/test_all_judge_modes.py standard     # STANDARD 分组
    python tests/test_all_judge_modes.py spj          # SPJ 分组
    python tests/test_all_judge_modes.py interactive  # INTERACTIVE 分组

依赖：Celery worker 必须已启动并连接 RabbitMQ。
"""

import json
import sys
import uuid

# ── 工具函数（从 judge_helper 导入） ──────────────────

from judge_helper import (
    LANG_CPP17,
    SOURCE_CPP_ECHO,
    SOURCE_CPP_WRONG,
    SOURCE_CPP_CE,
    SOURCE_CPP_TLE,
    SOURCE_CPP_MLE,
    SOURCE_CPP_OLE,
    SOURCE_CPP_RE,
    SOURCE_CPP_SPJ_AC,
    SOURCE_CPP_SPJ_WA,
    SPJ_CHECKER,
    SPJ_CHECKER_SIMPLE,
    INTERACTOR_SOURCE,
    USER_INT_AC,
    USER_INT_WA,
    USER_INT_RE,
    assert_result,
    build_payload,
    send_only,
    wait_result,
)


def send_and_await(submission_id: str, payload: dict, timeout: float = 15.0) -> dict:
    """发送判题请求并打印完整请求/响应。"""
    print(f"\n{'='*70}")
    print(f"[→] 已发送请求: {submission_id}  mode={payload.get('judge_mode')}")
    print(f"{'='*70}")
    print(f"[请求数据]")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    r = send_only(payload)
    response = wait_result(r, label=submission_id, timeout=timeout)

    print(f"\n[响应数据]")
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return response


# ── 测试函数 ─────────────────────────────────────────


def test_standard_acm_single_ac() -> bool:
    """STANDARD ACM: 单测点 AC"""
    sid = f"v-std-acm-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "hello world\n", "output_inline": "hello world\n",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "STANDARD ACM single AC")


def test_standard_acm_single_wa() -> bool:
    """STANDARD ACM: 单测点 WA"""
    sid = f"v-std-acm-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "expected output\n",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 0.0, "STANDARD ACM single WA")


def test_standard_acm_stop_on_first() -> bool:
    """STANDARD ACM: 首错即停 — 第1个AC, 第2个WA, 第3个应SKIPPED"""
    sid = f"v-std-acm-stop-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [
        {"case_no": 1, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": "wrong output\n"},
        {"case_no": 2, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": "expected\n"},
        {"case_no": 3, "points": 33.34, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": ""},
    ])
    result = send_and_await(sid, payload)
    cases = result.get("cases", [])
    ok = (len(cases) > 0 and cases[0].get("result") == "AC" and
          len(cases) > 1 and cases[1].get("result") == "WA" and
          len(cases) > 2 and cases[2].get("result") == "SKIPPED")
    print(f"  [{'PASS' if ok else 'FAIL'}] STANDARD ACM stop-on-first: "
          f"c1={cases[0].get('result') if len(cases)>0 else '?'} "
          f"c2={cases[1].get('result') if len(cases)>1 else '?'} "
          f"c3={cases[2].get('result') if len(cases)>2 else '?'}")
    return ok


def test_standard_oi_partial() -> bool:
    """STANDARD OI: partial=True 逐点累加 — 2AC+1WA → score≈66.66"""
    sid = f"v-std-oi-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [
        {"case_no": 1, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "a\n", "output_inline": "a\n"},
        {"case_no": 2, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "b\n", "output_inline": "b\n"},
        {"case_no": 3, "points": 33.34, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "c\n", "output_inline": "wrong\n"},
    ])
    payload["problem"]["partial"] = True
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 66.66, "STANDARD OI partial")


def test_standard_ioi_batch_depends() -> bool:
    """STANDARD IOI: batch2 依赖 batch1, batch1 中 WA → batch2 全部 SKIPPED"""
    sid = f"v-std-ioi-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [
        {"case_no": 1, "points": 25.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "a\n", "output_inline": "a\n", "batch_no": 1, "batch_depends": []},
        {"case_no": 2, "points": 25.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "b\n", "output_inline": "WRONG\n", "batch_no": 1, "batch_depends": []},
        {"case_no": 3, "points": 25.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "c\n", "output_inline": "c\n", "batch_no": 2, "batch_depends": [1]},
        {"case_no": 4, "points": 25.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "d\n", "output_inline": "d\n", "batch_no": 2, "batch_depends": [1]},
    ])
    result = send_and_await(sid, payload)
    cases = result.get("cases", [])
    c3 = cases[2].get("result") if len(cases) > 2 else "?"
    c4 = cases[3].get("result") if len(cases) > 3 else "?"
    ok = c3 == "SKIPPED" and c4 == "SKIPPED"
    print(f"  [{'PASS' if ok else 'FAIL'}] STANDARD IOI batch_depends: batch2=[{c3}, {c4}]")
    return ok


def test_standard_ce() -> bool:
    """STANDARD: 编译错误 → CE"""
    sid = f"v-std-ce-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_CE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "CE", 0.0, "STANDARD CE")


def test_standard_inline_data() -> bool:
    """STANDARD: 内联 input/output → AC"""
    sid = f"v-std-inline-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "test inline data\nline2\n",
        "output_inline": "test inline data\nline2\n",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "STANDARD inline data AC")


def test_spj_ac() -> bool:
    """SPJ: checker 返回 AC"""
    sid = f"v-spj-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER})
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "SPJ AC")


def test_spj_wa() -> bool:
    """SPJ: checker 返回 WA"""
    sid = f"v-spj-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_WA, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER})
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 0.0, "SPJ WA")


def test_interactive_ac() -> bool:
    """INTERACTIVE: 用户正确回复 → AC"""
    sid = f"v-int-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "INTERACTIVE AC")


def test_interactive_wa() -> bool:
    """INTERACTIVE: 用户输出错误 → WA"""
    sid = f"v-int-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_WA, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 0.0, "INTERACTIVE WA")


def test_interactive_re() -> bool:
    """INTERACTIVE: 用户程序崩溃 → RE"""
    sid = f"v-int-re-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_RE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    return assert_result(result, "RE", 0.0, "INTERACTIVE RE")


# ══════════════════════════════════════════════════════
# 新增测试：补齐所有缺失的状态路径
# ══════════════════════════════════════════════════════

def test_standard_re() -> bool:
    """STANDARD: 运行时崩溃 → RE"""
    sid = f"v-std-re-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_RE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "RE", 0.0, "STANDARD RE")


def test_standard_tle() -> bool:
    """STANDARD: 超时 → TLE"""
    sid = f"v-std-tle-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_TLE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 500, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "TLE", 0.0, "STANDARD TLE")


def test_standard_mle() -> bool:
    """STANDARD: 超内存 → MLE (用 Python 源码，cgroup 对 Python 更敏感)"""
    sid = f"v-std-mle-{uuid.uuid4().hex[:6]}"
    lang_py = dict(LANG_CPP17)
    lang_py.update(key="python3", name="Python3", extension=".py",
                   compile_command="", run_command="/usr/bin/python3 {source}")
    payload = build_payload(sid, "STANDARD", r"""
import sys
x = bytearray(180 * 1024 * 1024)
print(len(x))
""", lang_py, [{
    "case_no": 1, "points": 100.0,
    "time_limit_ms": 2000, "memory_limit_kb": 65536,
    "input_inline": "", "output_inline": "",
}])
    result = send_and_await(sid, payload)
    return assert_result(result, "MLE", 0.0, "STANDARD MLE")


def test_standard_ole() -> bool:
    """STANDARD: 超输出 → OLE（显式小 output_limit_bytes，避免先被 wall TLE）"""
    sid = f"v-std-ole-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_OLE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 5000, "memory_limit_kb": 262144,
        "output_limit_bytes": 1024,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload, timeout=30.0)
    actual = result.get("result")
    ok = actual == "OLE"
    print(f"  [{'PASS' if ok else 'FAIL'}] STANDARD OLE: result={actual} (expected OLE)")
    return ok


def test_standard_empty_cases() -> bool:
    """STANDARD: 无测试点 → FAILED"""
    sid = f"v-std-empty-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [])
    result = send_and_await(sid, payload)
    ok = result.get("status") == "FAILED" and result.get("result") is None
    print(f"  [{'PASS' if ok else 'FAIL'}] STANDARD empty cases: status={result.get('status')}")
    return ok


def test_spj_missing_source() -> bool:
    """SPJ: 缺 checker 源码 → FAILED"""
    sid = f"v-spj-missing-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }])
    result = send_and_await(sid, payload)
    ok = result.get("status") == "FAILED"
    print(f"  [{'PASS' if ok else 'FAIL'}] SPJ missing source: status={result.get('status')}")
    return ok


def test_spj_user_ce() -> bool:
    """SPJ: 用户程序编译错 → FAILED"""
    sid = f"v-spj-u-ce-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_CE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER_SIMPLE})
    result = send_and_await(sid, payload)
    ok = result.get("status") == "FAILED" and "编译失败" in (result.get("compile_output") or "")
    print(f"  [{'PASS' if ok else 'FAIL'}] SPJ user CE: status={result.get('status')}")
    return ok


def test_spj_checker_ce() -> bool:
    """SPJ: checker 编译错 → FAILED"""
    sid = f"v-spj-c-ce-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], spj={"language": LANG_CPP17, "source": "#include <broken"})
    result = send_and_await(sid, payload)
    ok = result.get("status") == "FAILED"
    print(f"  [{'PASS' if ok else 'FAIL'}] SPJ checker CE: status={result.get('status')}")
    return ok


def test_spj_user_re() -> bool:
    """SPJ: 用户程序运行时崩溃 → WA"""
    sid = f"v-spj-u-re-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_RE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER_SIMPLE})
    result = send_and_await(sid, payload)
    actual = result.get("result")
    ok = actual == "WA"
    print(f"  [{'PASS' if ok else 'FAIL'}] SPJ user RE: result={actual} (expected WA)")
    return ok


def test_interactive_ce() -> bool:
    """INTERACTIVE: 用户程序编译错 → CE"""
    sid = f"v-int-ce-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", SOURCE_CPP_CE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    cases = result.get("cases", [])
    ok = cases and cases[0].get("result") == "CE"
    print(f"  [{'PASS' if ok else 'FAIL'}] INTERACTIVE user CE: case_result={cases[0].get('result') if cases else '?'}")
    return ok


def test_interactive_interactor_ce() -> bool:
    """INTERACTIVE: 交互器编译错 → IE"""
    sid = f"v-int-ice-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": "#include <broken",
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    cases = result.get("cases", [])
    ok = cases and cases[0].get("result") == "IE"
    print(f"  [{'PASS' if ok else 'FAIL'}] INTERACTIVE interactor CE/IE: case_result={cases[0].get('result') if cases else '?'}")
    return ok


def test_interactive_missing_interactor() -> bool:
    """INTERACTIVE: 缺交互器源码 → FAILED"""
    sid = f"v-int-noint-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }])
    result = send_and_await(sid, payload)
    ok = result.get("status") == "FAILED"
    print(f"  [{'PASS' if ok else 'FAIL'}] INTERACTIVE missing interactor: status={result.get('status')}")
    return ok


# ── 运行入口 ──

ALL_TESTS = {
    "acm_ac": test_standard_acm_single_ac,
    "acm_wa": test_standard_acm_single_wa,
    "acm_stop": test_standard_acm_stop_on_first,
    "oi": test_standard_oi_partial,
    "ioi": test_standard_ioi_batch_depends,
    "ce": test_standard_ce,
    "inline": test_standard_inline_data,
    "re": test_standard_re,
    "tle": test_standard_tle,
    "mle": test_standard_mle,
    "ole": test_standard_ole,
    "empty_cases": test_standard_empty_cases,
    "spj_ac": test_spj_ac,
    "spj_wa": test_spj_wa,
    "spj_missing": test_spj_missing_source,
    "spj_user_ce": test_spj_user_ce,
    "spj_checker_ce": test_spj_checker_ce,
    "spj_user_re": test_spj_user_re,
    "int_ac": test_interactive_ac,
    "int_wa": test_interactive_wa,
    "int_re": test_interactive_re,
    "int_ce": test_interactive_ce,
    "int_ice": test_interactive_interactor_ce,
    "int_no_interactor": test_interactive_missing_interactor,
}

GROUPS = {
    "standard": ["acm_ac", "acm_wa", "acm_stop", "oi", "ioi", "ce", "inline",
                  "re", "tle", "mle", "ole", "empty_cases"],
    "spj": ["spj_ac", "spj_wa", "spj_missing", "spj_user_ce", "spj_checker_ce", "spj_user_re"],
    "interactive": ["int_ac", "int_wa", "int_re", "int_ce", "int_ice", "int_no_interactor"],
}

if __name__ == "__main__":
    group = sys.argv[1] if len(sys.argv) > 1 else "all"

    if group in GROUPS:
        test_names = GROUPS[group]
    elif group in ALL_TESTS:
        test_names = [group]
    else:
        test_names = list(ALL_TESTS.keys())

    print(f"\n{'#'*70}")
    print(f"# 判题模式全面测试 — {group} ({len(test_names)} tests)")
    print(f"{'#'*70}")

    results = {}
    for name in test_names:
        try:
            results[name] = ALL_TESTS[name]()
        except Exception as e:
            print(f"\n  [EXCEPTION] {name}: {e}")
            results[name] = False

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'='*70}")
    print(f"结果: {passed}/{total} 通过")
    if passed < total:
        failed = [k for k, v in results.items() if not v]
        print(f"失败: {', '.join(failed)}")
    print(f"{'='*70}")
    sys.exit(0 if passed == total else 1)
