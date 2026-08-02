"""Worker Sandbox Pool Celery 集成测试。

模拟真实判题请求，走完整 Celery → judge mode → SandboxClient → pool 链路。
所有测试通过 Celery `send_task("judge.execute")` 发送，通过 `AsyncResult.get()` 等待结果。

用法：
    cd acoj-worker
    python tests/test_celery_pool.py           # 全部
    python tests/test_celery_pool.py quick     # 快速（串行 20 + 并发 10 + TLE）
    python tests/test_celery_pool.py repeat    # 重复 3 轮全部测试（稳性验证）

依赖：Celery worker + Redis broker 必须已运行。
"""

import json
import os
import sys
import threading
import time
import uuid

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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
    LANG_PYTHON3,
    build_payload,
    send_only,
    wait_result,
    assert_result,
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
# C10: 串行 20 AC — 验证 pool 链路正确
# ══════════════════════════════════════════════════════


def test_c10_serial_20_ac():
    """通过 Celery 串行发送 20 个 AC 判题请求，验证 pool 复用。"""
    print("\n[ C10 ] 串行 20 AC (pool 复用验证)")
    for i in range(20):
        sid = f"c10-ac-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"hello {i}\n", "output_inline": f"hello {i}\n",
        }])
        result = wait_result(send_only(payload), label=sid, timeout=30.0)
        ok = assert_result(result, "AC", 100.0, f"C10 AC #{i}")
        report(f"C10 serial AC #{i}", ok)


# ══════════════════════════════════════════════════════
# C11: 并发 10 AC — 验证 pool 并发能力
# ══════════════════════════════════════════════════════


def test_c11_concurrent_10_ac():
    """10 个线程同时 send_only，验证 pool 未被压爆。"""
    print("\n[ C11 ] 并发 10 AC (pool 并发能力)")
    payloads = []
    for i in range(10):
        sid = f"c11-ac-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"x{i}\n", "output_inline": f"x{i}\n",
        }])
        payloads.append((sid, payload))

    # 批量发送（并发入队）
    print("  [→] 批量发送 10 个请求...")
    pending = [(sid, send_only(payload)) for sid, payload in payloads]

    # 逐一消费
    for sid, async_result in pending:
        result = wait_result(async_result, label=sid, timeout=30.0)
        ok = assert_result(result, "AC", 100.0, f"C11 AC {sid[-8:]}")
        report(f"C11 concurrent AC {sid[-8:]}", ok)


# ══════════════════════════════════════════════════════
# C12: TLE + AC 并行 — 修复 C4 偶发性失败
# ══════════════════════════════════════════════════════


def test_c12_tle_does_not_block():
    """TLE 和 AC 同时入队，验证 pool 不堵塞且 TLE 不影响 AC。"""
    print("\n[ C12 ] TLE + AC 并行 (pool 防堵塞)")
    sid_tle = f"c12-tle-{uuid.uuid4().hex[:6]}"
    sid_ac = f"c12-ac-{uuid.uuid4().hex[:6]}"

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

    r_tle = send_only(payload_tle)
    r_ac = send_only(payload_ac)
    print("  [→] 已同时发送 TLE 和 AC 请求")
    import sys; sys.stdout.flush()

    # 任务并发发送即可验证 worker/pool 并行；rpc:// result backend 不支持稳定的
    # 多线程并发 get，同进程内按顺序消费可避免结果队列竞态造成假失败。
    tle_raw = wait_result(r_tle, label="tle", timeout=25.0)
    ac_raw = wait_result(r_ac, label="ac", timeout=25.0)
    tle_r = tle_raw.get("result")
    ac_r = ac_raw.get("result")

    ok_tle = tle_r == "TLE"
    ok_ac = ac_r == "AC"
    report("C12 TLE: result=" + (tle_r or "?"), ok_tle)
    report("C12 AC after TLE: result=" + (ac_r or "?"), ok_ac)


# ══════════════════════════════════════════════════════
# C13: 混合模式 10 个 — STANDARD/SPJ/INTERACTIVE
# ══════════════════════════════════════════════════════


def test_c13_mixed_modes():
    """混合 10 个不同模式同 request，验证 pool 多语言配置正确。"""
    print("\n[ C13 ] 混合 10 模式 (STANDARD/SPJ/INTERACTIVE)")
    entries: list[tuple[str, str, dict, str, float]] = []

    # 5x STANDARD AC
    for i in range(5):
        sid = f"c13-std-ac-{i}-{uuid.uuid4().hex[:6]}"
        entries.append((sid, f"STD AC #{i}",
            build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": f"y{i}\n", "output_inline": f"y{i}\n",
            }]), "AC", 100.0))

    # STANDARD WA
    sid = f"c13-std-wa-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "STD WA",
        build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": "expected\n",
        }]), "WA", 0.0))

    # STANDARD RE
    sid = f"c13-std-re-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "STD RE",
        build_payload(sid, "STANDARD", SOURCE_CPP_RE, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": "",
        }]), "RE", 0.0))

    # SPJ AC
    sid = f"c13-spj-ac-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "SPJ AC",
        build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": None,
        }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER}),
        "AC", 100.0))

    # INTERACTIVE AC
    sid = f"c13-int-ac-{uuid.uuid4().hex[:6]}"
    entries.append((sid, "INT AC",
        build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": None,
        }], interactor={
            "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
            "time_limit_ms": 4000, "memory_limit_kb": 262144,
        }), "AC", 100.0))

    # 批量发送
    print("  [→] 批量发送 10 个混合请求...")
    pending = [(sid, label, exp_result, exp_score, send_only(payload))
               for sid, label, payload, exp_result, exp_score in entries]

    for sid, label, exp_result, exp_score, async_result in pending:
        result = wait_result(async_result, label=f"C13 {label}", timeout=30.0)
        ok = assert_result(result, exp_result, exp_score, label)
        report(f"C13 {label}", ok)


# ══════════════════════════════════════════════════════
# C15: Python 脚本判题（非编译型语言）
# ══════════════════════════════════════════════════════


def test_c15_python_judge():
    """Python 脚本通过 pool 判题（编译型/脚本型语言混合）。"""
    print("\n[ C15 ] Python 脚本判题")
    for i in range(10):
        sid = f"c15-py-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD",
            f"print({i})", LANG_PYTHON3, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 5000, "memory_limit_kb": 262144,
                "input_inline": "", "output_inline": f"{i}\n",
            }])
        result = wait_result(send_only(payload), label=sid, timeout=30.0)
        ok = assert_result(result, "AC", 100.0, f"C15 Python #{i}")
        report(f"C15 Python #{i}", ok)


# ══════════════════════════════════════════════════════
# ── 运行入口 ──
# ══════════════════════════════════════════════════════

ALL_TESTS = [
    ("C10 串行 20 AC", test_c10_serial_20_ac),
    ("C11 并发 10 AC", test_c11_concurrent_10_ac),
    ("C12 TLE+AC 并行", test_c12_tle_does_not_block),
    ("C13 混合 10 模式", test_c13_mixed_modes),
    ("C15 Python 判题", test_c15_python_judge),
]


def run_all(prefix="C"):
    for name, func in ALL_TESTS:
        try:
            func()
        except Exception as e:
            print(f"\n  [EXCEPTION] {name}: {e}", file=sys.stderr)
            report(f"{name} (exception)", False)


def run_once(prefix=""):
    reset_counters()
    run_all(prefix)
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"结果: {PASS}/{total} 通过", end="")
    if FAIL:
        print(f", {FAIL} 失败")
    else:
        print()
    print(f"{'='*60}")
    return FAIL == 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "repeat":
        print("=" * 60)
        print("C14: 重复 3 轮测试 — 稳定性验证")
        print("=" * 60)
        all_ok = True
        for round_i in range(3):
            print(f"\n{'#'*60}")
            print(f"# 第 {round_i+1} 轮")
            print(f"{'#'*60}")
            ok = run_once()
            if not ok:
                all_ok = False
        final = "ALL PASS" if all_ok else "SOME ROUNDS FAILED"
        print(f"\n{'='*60}")
        print(f"C14 稳定验证: {final}")
        print(f"{'='*60}")
        sys.exit(0 if all_ok else 1)
    elif mode == "quick":
        # 只跑串行 20 + 并发 10 + TLE
        reset_counters()
        test_c10_serial_20_ac()
        test_c11_concurrent_10_ac()
        test_c12_tle_does_not_block()
        total = PASS + FAIL
        print(f"\n{'='*60}")
        print(f"Quick: {PASS}/{total} 通过", end="")
        if FAIL:
            print(f", {FAIL} 失败")
        else:
            print()
        print(f"{'='*60}")
        sys.exit(0 if FAIL == 0 else 1)
    else:
        ok = run_once()
        sys.exit(0 if ok else 1)
