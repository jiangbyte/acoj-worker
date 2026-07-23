"""Worker 并发判题压力测试。

测试场景：
- C2: 顺序并发 10 个 AC — 发送 10 个 AC submission，全部返回 AC
- C3: 混合并发 10 个 — AC/WA/RE/TLE/SPJ/INTERACTIVE 混合，验证每个正确
- C4: TLE 不影响后续 — TLE submission 后面立即发一个 AC，AC 必须正常判题
"""

import sys
import threading
import uuid

from judge_helper import (
    LANG_CPP17,
    SOURCE_CPP_ECHO,
    SOURCE_CPP_WRONG,
    SOURCE_CPP_TLE,
    SOURCE_CPP_RE,
    SOURCE_CPP_SPJ_AC,
    SPJ_CHECKER,
    INTERACTOR_SOURCE,
    USER_INT_AC,
    build_payload,
    send_only,
    wait_result,
    assert_result,
)

PASS = 0
FAIL = 0
lock = threading.Lock()


def report(label: str, ok: bool):
    global PASS, FAIL
    with lock:
        if ok:
            PASS += 1
            print(f"  [PASS] {label}")
        else:
            FAIL += 1
            print(f"  [FAIL] {label}")


# ── C2: 顺序并发 10 个 AC ─────────────────────────────

def test_c2_sequential_10_ac():
    """10 个 AC submission 串行连续发送"""
    print("\n[ C2 ] 顺序并发 10 AC")
    for i in range(10):
        sid = f"c2-ac-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"hello {i}\n", "output_inline": f"hello {i}\n",
        }])
        result = wait_result(send_only(payload), label=sid, timeout=15.0)
        ok = assert_result(result, "AC", 100.0, f"SEQ-AC-{i}")
        report(f"C2 sequential AC #{i}", ok)


# ── C3: 混合并发 ─────────────────────────────────────

def test_c3_mixed_concurrent():
    """混合 10 个不同判题模式/结果：先批量发送，再逐一消费结果"""
    print("\n[ C3 ] 混合并发 10 请求")

    entries: list[tuple[str, str, dict, str, float]] = []

    # 5 个 STANDARD AC
    for i in range(5):
        sid = f"c3-std-ac-{i}-{uuid.uuid4().hex[:6]}"
        entries.append((sid, f"STANDARD AC #{i}",
            build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": f"x{i}\n", "output_inline": f"x{i}\n",
            }]), "AC", 100.0))

    # STANDARD WA
    sid = f"c3-std-wa-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "STANDARD WA",
        build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": "expected\n",
        }]), "WA", 0.0))

    # STANDARD RE
    sid = f"c3-std-re-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "STANDARD RE",
        build_payload(sid, "STANDARD", SOURCE_CPP_RE, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": "",
        }]), "RE", 0.0))

    # SPJ AC
    sid = f"c3-spj-ac-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "SPJ AC",
        build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": None,
        }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER}),
        "AC", 100.0))

    # INTERACTIVE AC
    sid = f"c3-int-ac-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "INTERACTIVE AC",
        build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": None,
        }], interactor={
            "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
            "time_limit_ms": 4000, "memory_limit_kb": 262144,
        }), "AC", 100.0))

    WA_SOURCE = r"""#include <iostream>
#include <string>
int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hi, " << name << "!" << std::endl;
    return 0;
}"""
    sid = f"c3-int-wa-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "INTERACTIVE WA",
        build_payload(sid, "INTERACTIVE", WA_SOURCE, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": None,
        }], interactor={
            "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
            "time_limit_ms": 4000, "memory_limit_kb": 262144,
        }), "WA", 0.0))

    # Step 1: 批量发送
    print("  [→] 批量发送 10 个请求...")
    pending = [(sid, label, exp_result, exp_score, send_only(payload))
               for sid, label, payload, exp_result, exp_score in entries]

    # Step 2: 逐一消费
    for sid, label, exp_result, exp_score, async_result in pending:
        result = wait_result(async_result, label=f"C3 {label}", timeout=30.0)
        ok = assert_result(result, exp_result, exp_score, label)
        report(f"C3 {label}", ok)


# ── C4: TLE 不影响后续 ──────────────────────────────

def test_c4_tle_does_not_block():
    """TLE 不应该阻塞后续正常判题"""
    print("\n[ C4 ] TLE 不影响后续")

    sid_tle = f"c4-tle-{uuid.uuid4().hex[:6]}"
    sid_ac = f"c4-ac-{uuid.uuid4().hex[:6]}"

    payload_tle = build_payload(sid_tle, "STANDARD", SOURCE_CPP_TLE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 500, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    payload_ac = build_payload(sid_ac, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "ok\n", "output_inline": "ok\n",
    }])

    # 批量发送（TLE 和 AC 同时入队）
    r_tle = send_only(payload_tle)
    r_ac = send_only(payload_ac)
    print("  [→] 已同时发送 TLE 和 AC 请求")

    # 任务并发发送即可验证 worker/pool 并行；rpc:// result backend 不支持稳定的
    # 多线程并发 get，同进程内按顺序消费可避免结果队列竞态造成假失败。
    tle_r = wait_result(r_tle, label="tle", timeout=25.0).get("result")
    ac_r = wait_result(r_ac, label="ac", timeout=25.0).get("result")

    ok_tle = tle_r == "TLE"
    ok_ac = ac_r == "AC"

    if ok_tle:
        print(f"  [PASS] C4 TLE: result=TLE")
    else:
        print(f"  [FAIL] C4 TLE: result={tle_r} (expected TLE)")
    if ok_ac:
        print(f"  [PASS] C4 AC after TLE: result=AC")
    else:
        print(f"  [FAIL] C4 AC after TLE: result={ac_r} (expected AC)")

    global PASS, FAIL
    with lock:
        PASS += (1 if ok_tle else 0) + (1 if ok_ac else 0)
        FAIL += (0 if ok_tle else 1) + (0 if ok_ac else 1)


if __name__ == "__main__":
    print("=" * 60)
    print("Worker 并发判题压力测试")
    print("=" * 60)

    test_c2_sequential_10_ac()
    test_c3_mixed_concurrent()
    test_c4_tle_does_not_block()

    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"结果: {PASS}/{total} 通过", end="")
    if FAIL:
        print(f", {FAIL} 失败")
    else:
        print()
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)
