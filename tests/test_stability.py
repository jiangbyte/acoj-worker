"""Worker 持久运行稳定性测试。

C8: 连续 10 轮 x 5 个 AC burst + TLE 混合，检查内存/进程稳定性。
"""

import subprocess
import sys
import time
import uuid

from judge_helper import (
    LANG_CPP17, SOURCE_CPP_ECHO, SOURCE_CPP_TLE,
    build_payload, send_only, wait_result,
)

PASS = 0
FAIL = 0


def report(label: str, ok: bool):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def get_worker_memory() -> int:
    try:
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split("\n"):
            if "app.main" in line and "grep" not in line:
                parts = line.split()
                if len(parts) >= 6:
                    return int(parts[5])
    except Exception:
        pass
    return 0


def test_c8_stability():
    print("\n[ C8 ] 持久稳定性 (10 轮脉冲)")

    mem_before = get_worker_memory()
    print(f"  [->] 初始内存: {mem_before}KB")

    total_ac = 0
    total_tle = 0

    for round_i in range(10):
        step_start = time.time()

        ac_sids = [f"c8-burst-{round_i}-{i}-{uuid.uuid4().hex[:6]}" for i in range(5)]

        ac_payloads = []
        for sid in ac_sids:
            payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
                "case_no": 1, "points": 100.0,
                "time_limit_ms": 2000, "memory_limit_kb": 262144,
                "input_inline": f"round{round_i}\n", "output_inline": f"round{round_i}\n",
            }])
            ac_payloads.append((sid, send_only(payload)))

        sid_tle = f"c8-tle-{round_i}-{uuid.uuid4().hex[:6]}"
        tle_payload = build_payload(sid_tle, "STANDARD", SOURCE_CPP_TLE, LANG_CPP17, [{
            "case_no": 1, "points": 100.0,
            "time_limit_ms": 500, "memory_limit_kb": 262144,
            "input_inline": "", "output_inline": "",
        }])
        tle_result = send_only(tle_payload)

        # 消费结果
        for sid, async_result in ac_payloads:
            r = wait_result(async_result, label=sid, timeout=20.0)
            result = r.get("result")
            if result == "AC":
                total_ac += 1
            else:
                print(f"  [FAIL] round {round_i} AC: sid={sid[-8:]} result={result}")
                FAIL += 1

        r = wait_result(tle_result, label=sid_tle, timeout=20.0)
        result = r.get("result")
        if result == "TLE":
            total_tle += 1
        else:
            print(f"  [FAIL] round {round_i} TLE: result={result}")
            FAIL += 1

        elapsed_ms = int((time.time() - step_start) * 1000)
        print(f"  [->] round {round_i}: 5AC+1TLE in {elapsed_ms}ms")

    mem_after = get_worker_memory()
    print(f"  [->] 最终内存: {mem_after}KB (diff: {mem_after - mem_before}KB)")

    report(f"C8 {total_ac} AC verdicts correct", total_ac == 50)
    report(f"C8 {total_tle} TLE verdicts correct", total_tle == 10)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"], capture_output=True).returncode == 0
    report("C8 worker alive after stability test", alive)

    increase_pct = (mem_after - mem_before) / max(mem_before, 1) * 100
    no_leak = increase_pct < 30
    report(f"C8 memory stable ({increase_pct:+.1f}%)", no_leak)


if __name__ == "__main__":
    print("=" * 60)
    print("Worker 持久运行稳定性测试 (C8)")
    print("=" * 60)

    test_c8_stability()

    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"结果: {PASS}/{total} 通过", end="")
    if FAIL:
        print(f", {FAIL} 失败")
    else:
        print()
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)
