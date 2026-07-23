"""Worker 并发吞吐增强测试。

C16: 50 并发 AC — 批量发送后串行消费，验证全部 AC
C17: 100 串行 burst — 连续快速发送，验证 pool 吞吐
C18: 30 并发混合模式 — 10 STANDARD + 10 SPJ + 10 INTERACTIVE 同时发送
"""

import sys
import threading
import uuid

from judge_helper import (
    LANG_CPP17,
    SOURCE_CPP_ECHO,
    SOURCE_CPP_SPJ_AC,
    SPJ_CHECKER,
    INTERACTOR_SOURCE,
    USER_INT_AC,
    build_payload,
    send_only,
    wait_result,
)

PASS = 0
FAIL = 0
result_lock = threading.Lock()


def report(label: str, ok: bool):
    global PASS, FAIL
    with result_lock:
        if ok:
            PASS += 1
            print(f"  [PASS] {label}")
        else:
            FAIL += 1
            print(f"  [FAIL] {label}")


def reset_counters():
    global PASS, FAIL
    PASS = 0
    FAIL = 0


# ══════════════════════════════════════════════════════
# C16: 50 并发 AC
# ══════════════════════════════════════════════════════


def test_c16_50_concurrent_ac():
    """50 个请求同时发送（批量入队），串行消费结果，验证全部 AC。"""
    print("\n[ C16 ] 50 并发 AC")
    payloads = []
    for i in range(50):
        sid = f"c16-con-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"x{i}\n", "output_inline": f"x{i}\n",
        }])
        payloads.append((sid, payload))

    print("  [→] 批量发送 50 个请求...")
    pending = [(sid, send_only(payload)) for sid, payload in payloads]

    ok = 0
    for sid, async_result in pending:
        try:
            result = wait_result(async_result, label=sid, timeout=60.0)
            if result.get("result") == "AC":
                ok += 1
            report(f"C16 #{sid[-8:]}", result.get("result") == "AC")
        except Exception as e:
            report(f"C16 #{sid[-8:]}: timeout", False)

    print(f"  [i] C16: {ok}/50 AC")


# ══════════════════════════════════════════════════════
# C17: 100 串行 burst
# ══════════════════════════════════════════════════════


def test_c17_100_serial_burst():
    """100 个 AC 请求连续串行发送，验证 pool 高吞吐。"""
    print("\n[ C17 ] 100 串行 burst")
    ok = 0
    for i in range(100):
        sid = f"c17-burst-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"burst{i}\n", "output_inline": f"burst{i}\n",
        }])
        try:
            result = wait_result(send_only(payload), label=sid, timeout=30.0)
            passed = result.get("result") == "AC"
            if passed:
                ok += 1
            report(f"C17 #{i}", passed)
        except Exception as e:
            report(f"C17 #{i}: timeout", False)

    print(f"  [i] C17: {ok}/100 AC")


# ══════════════════════════════════════════════════════
# C18: 30 并发混合模式
# ══════════════════════════════════════════════════════


def test_c18_30_concurrent_mixed():
    """10 STANDARD + 10 SPJ + 10 INTERACTIVE 同时发送。"""
    print("\n[ C18 ] 30 并发混合模式 (10 STD + 10 SPJ + 10 INT)")
    entries = []

    # 10 STANDARD AC
    for i in range(10):
        sid = f"c18-std-{i}-{uuid.uuid4().hex[:6]}"
        entries.append((sid, "STD",
            build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": f"z{i}\n", "output_inline": f"z{i}\n",
            }]), "AC", 100.0))

    # 10 SPJ AC
    for i in range(10):
        sid = f"c18-spj-{i}-{uuid.uuid4().hex[:6]}"
        entries.append((sid, "SPJ",
            build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": "", "output_inline": None,
            }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER}),
            "AC", 100.0))

    # 10 INTERACTIVE AC
    for i in range(10):
        sid = f"c18-int-{i}-{uuid.uuid4().hex[:6]}"
        entries.append((sid, "INT",
            build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": "", "output_inline": None,
            }], interactor={
                "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
                "time_limit_ms": 4000, "memory_limit_kb": 262144,
            }), "AC", 100.0))

    print("  [→] 批量发送 30 个混合请求...")
    pending = [(sid, tag, exp, send_only(payload))
               for sid, tag, payload, exp, _score in entries]

    for sid, tag, exp, async_result in pending:
        try:
            result = wait_result(async_result, label=sid, timeout=60.0)
            passed = result.get("result") == exp
            report(f"C18 {tag} {sid[-8:]}", passed)
        except Exception as e:
            report(f"C18 {tag} {sid[-8:]}: timeout", False)


# ══════════════════════════════════════════════════════
# ── 运行入口 ──
# ══════════════════════════════════════════════════════

ALL_TESTS = [
    ("C16 50 并发 AC", test_c16_50_concurrent_ac),
    ("C17 100 串行 burst", test_c17_100_serial_burst),
    ("C18 30 并发混合", test_c18_30_concurrent_mixed),
]


def run_all():
    reset_counters()
    for name, func in ALL_TESTS:
        try:
            func()
        except Exception as e:
            print(f"\n  [EXCEPTION] {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    print("=" * 60)
    print("Worker 并发吞吐增强测试 (C16-C18)")
    print("=" * 60)
    run_all()
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"结果: {PASS}/{total} 通过", end="")
    if FAIL:
        print(f", {FAIL} 失败")
    else:
        print()
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)
