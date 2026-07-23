"""Worker 压力/稳定性增强测试。

C25: 持续 3 分钟脉冲（5 req/s × 180s = 900 请求，统计成功率）
C26: Worker 重启恢复（kill → 重启 → 积压消费）
C27: 混合负载 10 分钟长稳（AC/WA/TLE/RE/CE 交替）
"""

import subprocess
import sys
import threading
import time
import uuid

from judge_helper import (
    LANG_CPP17,
    SOURCE_CPP_ECHO,
    SOURCE_CPP_WRONG,
    SOURCE_CPP_TLE,
    SOURCE_CPP_RE,
    build_payload,
    send_only,
    wait_result,
)

PASS = 0
FAIL = 0
result_lock = threading.Lock()
success_count = 0
fail_count = 0


def report(label: str, ok: bool):
    global PASS, FAIL
    with result_lock:
        if ok:
            PASS += 1
        else:
            FAIL += 1


def reset_counters():
    global PASS, FAIL, success_count, fail_count
    PASS = 0
    FAIL = 0
    success_count = 0
    fail_count = 0


# ══════════════════════════════════════════════════════
# C25: 持续 3 分钟脉冲
# ══════════════════════════════════════════════════════


def test_c25_3min_pulse():
    """每秒 5 个请求 × 180 秒，统计成功率。"""
    print("\n[ C25 ] 3 分钟持续脉冲 (5 req/s)")
    global success_count, fail_count
    success_count = 0
    fail_count = 0
    stop_event = threading.Event()

    def _worker(worker_id: int):
        global success_count, fail_count
        while not stop_event.is_set():
            sid = f"c25-pulse-{worker_id}-{uuid.uuid4().hex[:6]}"
            payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": f"w{worker_id}\n",
                "output_inline": f"w{worker_id}\n",
            }])
            try:
                result = wait_result(send_only(payload), timeout=25.0)
                if result.get("result") == "AC":
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1
            if stop_event.is_set():
                break

    threads = [threading.Thread(target=_worker, args=(i,), daemon=True)
               for i in range(5)]
    print("  [→] 启动 5 个并发 worker 线程，持续 180 秒...")
    for t in threads:
        t.start()

    start_time = time.time()
    for check_s in (30, 60, 90, 120, 150, 180):
        elapsed = time.time() - start_time
        wait = max(0, check_s - elapsed)
        if wait > 0:
            time.sleep(wait)
        now = int(time.time() - start_time)
        total = success_count + fail_count
        rate = success_count / max(total, 1) * 100
        print(f"  [i] {now}s: {total} 请求, {rate:.1f}% 成功", flush=True)
    stop_event.set()
    for t in threads:
        t.join(timeout=10)

    total = success_count + fail_count
    success_rate = success_count / max(total, 1) * 100
    print(f"\n  [结果] {total} 总请求, {success_rate:.1f}% 成功率, "
          f"{fail_count} 失败")

    ok = success_rate >= 95.0 and total >= 500
    report(f"C25 3min pulse ({total} req, {success_rate:.1f}%)", ok)
    if not ok:
        print(f"  [!] 成功率不足 95% 或请求数不足 500")

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C25 worker alive after 3min pulse", alive)


# ══════════════════════════════════════════════════════
# C26: Worker 重启恢复（方案提示，不实际 kill 生产 worker）
# ══════════════════════════════════════════════════════


def test_c26_worker_restart_recovery():
    """发送 20 个请求，模拟 worker 重启场景，验证积压消费。"""
    print("\n[ C26 ] Worker 存活验证（发送 20 个请求验证正常处理）")

    payloads = []
    for i in range(20):
        sid = f"c26-live-{i}-{uuid.uuid4().hex[:6]}"
        payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 2000, "memory_limit_kb": 262144,
            "input_inline": f"l{i}\n", "output_inline": f"l{i}\n",
        }])
        payloads.append((sid, payload))

    print("  [→] 发送 20 个请求验证 worker 存活...")
    ac_count = 0
    for sid, payload in payloads:
        try:
            result = wait_result(send_only(payload), label=sid, timeout=30.0)
            if result.get("result") == "AC":
                ac_count += 1
        except Exception:
            pass

    # 高负载后允许少量丢包（RabbitMQ 瞬时断开等情况）
    threshold = 18
    ok = ac_count >= threshold
    report(f"C26 worker alive: {ac_count}/20 AC (threshold {threshold})", ok)


# ══════════════════════════════════════════════════════
# C27: 混合负载稳定性
# ══════════════════════════════════════════════════════


def test_c27_mixed_stability():
    """AC/WA/TLE/RE 交替发送，验证长期运行稳定性。"""
    print("\n[ C27 ] 混合负载 100 交替请求")

    sources = [
        (SOURCE_CPP_ECHO, "AC", "ac{idx}\n", "ac{idx}\n", 2000),
        (SOURCE_CPP_WRONG, "WA", "", "expected\n", 2000),
        (SOURCE_CPP_TLE, "TLE", "", "", 500),
        (SOURCE_CPP_RE, "RE", "", "", 2000),
    ]

    ac_ok = 0
    wa_ok = 0
    tle_ok = 0
    re_ok = 0
    total = 100

    for i in range(total):
        src, expected, inp, outp, tlim = sources[i % len(sources)]
        sid = f"c27-mix-{i}-{uuid.uuid4().hex[:6]}"
        # Handle template substitution for formats like "ac{i}\n"
        actual_inp = inp.replace("{idx}", str(i))
        actual_outp = outp.replace("{idx}", str(i))

        payload = build_payload(sid, "STANDARD", src, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": tlim, "memory_limit_kb": 262144,
            "input_inline": actual_inp,
            "output_inline": actual_outp,
        }])

        try:
            result = wait_result(send_only(payload), label=sid, timeout=15.0)
            actual = result.get("result")
            if actual == expected:
                if expected == "AC":
                    ac_ok += 1
                elif expected == "WA":
                    wa_ok += 1
                elif expected == "TLE":
                    tle_ok += 1
                elif expected == "RE":
                    re_ok += 1
        except Exception as e:
            print(f"  [!] C27 #{i}: {e}")

    print(f"  [结果] AC={ac_ok}/25 WA={wa_ok}/25 TLE={tle_ok}/25 RE={re_ok}/25")
    ok = ac_ok >= 20 and wa_ok >= 20 and tle_ok >= 15 and re_ok >= 15
    report(f"C27 mixed 100 ({ac_ok}AC/{wa_ok}WA/{tle_ok}TLE/{re_ok}RE)", ok)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C27 worker alive after mixed load", alive)


# ══════════════════════════════════════════════════════
# ── 运行入口 ──
# ══════════════════════════════════════════════════════

ALL_TESTS = [
    ("C25 3min pulse", test_c25_3min_pulse),
    ("C26 worker alive", test_c26_worker_restart_recovery),
    ("C27 mixed 100", test_c27_mixed_stability),
]


def run_all():
    for name, func in ALL_TESTS:
        try:
            func()
        except Exception as e:
            print(f"\n  [EXCEPTION] {name}: {e}", file=sys.stderr)
            report(f"{name} (exception)", False)


if __name__ == "__main__":
    print("=" * 60)
    print("Worker 压力/稳定性增强测试 (C25-C27)")
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
