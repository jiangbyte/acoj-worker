#!/usr/bin/env python3
"""Worker 性能基准测试：测量吞吐、延迟、混合负载。

使用 Celery task judge.execute，针对真实 RabbitMQ + Celery worker 运行。

运行要求：
  - Celery worker + RabbitMQ 必须运行
  - acoj-sandbox Python 包已安装
  - 当前目录是 acoj-worker 项目根

三种测试模式（各语言分别跑）：
  1. Burst AC    - 64 个 AC 任务并发请求，测吞吐 + 延迟分布
  2. Sustained   - 4 线程持续 60s 发 AC 任务，测稳定吞吐
  3. Mixed       - AC + TLE + WA 混合，测 TLE 不阻塞正常判题
"""

import json
import os
import sys
import threading
import time
import uuid
from collections import OrderedDict

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from judge_helper import (
    LANG_CPP17,
    LANG_PYTHON3,
    SOURCE_CPP_ECHO,
    SOURCE_CPP_TLE,
    SOURCE_CPP_WRONG,
    SOURCE_CPP_SPJ_AC,
    USER_INT_AC,
    USER_INT_PY_AC,
    SPJ_CHECKER,
    INTERACTOR_SOURCE,
    build_payload,
    send_only,
    wait_result,
)

# ── Sources ──
SOURCE_PY_ECHO = "import sys\nfor line in sys.stdin: sys.stdout.write(line)"
SOURCE_PY_TLE = "import sys\nwhile True: pass"
SOURCE_PY_WRONG = "import sys\nprint('wrong')"

LANGUAGES = OrderedDict([
    ("C++", (LANG_CPP17, {
        "echo": SOURCE_CPP_ECHO,
        "tle": SOURCE_CPP_TLE,
        "wrong": SOURCE_CPP_WRONG,
    })),
    ("Python", (LANG_PYTHON3, {
        "echo": SOURCE_PY_ECHO,
        "tle": SOURCE_PY_TLE,
        "wrong": SOURCE_PY_WRONG,
    })),
])

# ── 判题模式配置 ──

# SPJ: checker 固定用 C++ testlib，用户程序可以 C++ 或 Python
SPJ_EXTRA = {
    "C++": {"spj": {"language": LANG_CPP17, "source": SPJ_CHECKER}},
    "Python": {"spj": {"language": LANG_CPP17, "source": SPJ_CHECKER}},
}

INTERACTOR_EXTRA = {
    "C++": {"interactor": {"language": LANG_CPP17, "source": INTERACTOR_SOURCE,
                           "time_limit_ms": 4000, "memory_limit_kb": 262144}},
    "Python": {"interactor": {"language": LANG_CPP17, "source": INTERACTOR_SOURCE, "time_limit_ms": 4000, "memory_limit_kb": 262144}},

}

RESULT_TIMEOUT = 30.0
BURST_COUNT = 64
SUSTAINED_DURATION = 60
SUSTAINED_THREADS = 4
MIXED_AC = 20
MIXED_TLE = 3
MIXED_WA = 5
SPJ_COUNT = 16
INT_COUNT = 16


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    k = (n - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < n:
        return s[f] * (1 - c) + s[f + 1] * c
    return s[f]


# ── Test 1: Burst AC ──


def run_burst_ac(lang_name: str, lang_cfg: dict, sources: dict) -> dict:
    count = BURST_COUNT
    print(f"  [Burst AC] sending {count} AC tasks...")
    payloads = []
    for i in range(count):
        sid = f"bench-burst-{i}-{uuid.uuid4().hex[:6]}"
        payloads.append(
            build_payload(sid, "STANDARD", sources["echo"], lang_cfg, [
                {"case_no": 1, "points": 100.0, "time_limit_ms": 2000,
                 "memory_limit_kb": 262144, "input_inline": f"x{i}\n",
                 "output_inline": f"x{i}\n"},
            ])
        )

    latencies: list[float] = []
    verdicts: list[str] = []
    cpu_times: list[int] = []

    async_results = [send_only(p) for p in payloads]
    t0 = time.monotonic()
    t_wait_start = time.monotonic()
    for i, ar in enumerate(async_results):
        t1 = time.monotonic()
        resp = wait_result(ar, timeout=RESULT_TIMEOUT)
        t2 = time.monotonic()
        latencies.append((t2 - t1) * 1000)
        verdicts.append(resp.get("result", "?"))
        cpu_times.append(resp.get("time_ms", 0))
    t_end = time.monotonic()

    duration = t_end - t0
    success = sum(1 for v in verdicts if v == "AC")
    result = {
        "success": success,
        "failed": count - success,
        "duration_sec": round(duration, 2),
        "throughput_req_per_sec": round(count / duration, 2),
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
        "latency_min_ms": round(min(latencies), 1),
        "latency_max_ms": round(max(latencies), 1),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1),
        "latencies_flat": [round(v, 1) for v in latencies],
        "cpu_time_mean_ms": round(sum(cpu_times) / len(cpu_times), 1),
    }
    print(f"    throughput: {result['throughput_req_per_sec']} req/s  "
          f"latency P50={result['latency_p50_ms']} P95={result['latency_p95_ms']} P99={result['latency_p99_ms']}ms  "
          f"success: {success}/{count}")
    return result


# ── Test 2: Sustained ──


def run_sustained(lang_name: str, lang_cfg: dict, sources: dict) -> dict:
    print(f"  [Sustained] {SUSTAINED_THREADS} threads × {SUSTAINED_DURATION}s...")
    lock = threading.Lock()
    total = success = fail = 0
    stop = threading.Event()

    def _worker(wid: int):
        nonlocal total, success, fail
        while not stop.is_set():
            sid = f"bench-sust-{wid}-{uuid.uuid4().hex[:6]}"
            payload = build_payload(
                sid, "STANDARD", sources["echo"], lang_cfg, [
                    {"case_no": 1, "points": 100.0, "time_limit_ms": 2000,
                     "memory_limit_kb": 262144, "input_inline": f"w{wid}\n",
                     "output_inline": f"w{wid}\n"},
                ]
            )
            try:
                resp = wait_result(send_only(payload), timeout=RESULT_TIMEOUT)
                with lock:
                    total += 1
                    if resp.get("result") == "AC":
                        success += 1
                    else:
                        fail += 1
            except Exception:
                with lock:
                    total += 1
                    fail += 1

    threads = [threading.Thread(target=_worker, args=(i,), daemon=True) for i in range(SUSTAINED_THREADS)]
    t0 = time.monotonic()
    for t in threads: t.start()
    time.sleep(SUSTAINED_DURATION)
    stop.set()
    for t in threads: t.join(timeout=10)
    duration = time.monotonic() - t0

    result = {
        "duration_sec": round(duration, 2),
        "total": total, "success": success, "failed": fail,
        "throughput_req_per_sec": round(total / duration, 2),
    }
    print(f"    {total} req, {result['throughput_req_per_sec']} req/s, {success}/{total} success")
    return result


# ── Test 3: Mixed ──


def run_mixed(lang_name: str, lang_cfg: dict, sources: dict) -> dict:
    print(f"  [Mixed] AC={MIXED_AC} TLE={MIXED_TLE} WA={MIXED_WA}...")
    specs = [
        ("AC", sources["echo"], MIXED_AC, 2000),
        ("TLE", sources["tle"], MIXED_TLE, 500),
        ("WA", sources["wrong"], MIXED_WA, 2000),
    ]
    payloads = []
    for verdict, src, cnt, tl in specs:
        for i in range(cnt):
            sid = f"bench-mix-{verdict}-{i}-{uuid.uuid4().hex[:6]}"
            payloads.append((verdict, build_payload(
                sid, "STANDARD", src, lang_cfg,
                [{"case_no": 1, "points": 100.0, "time_limit_ms": tl,
                  "memory_limit_kb": 262144, "input_inline": f"x{i}\n",
                  "output_inline": f"x{i}\n"}],
            )))

    t0 = time.monotonic()
    async_results = [(v, send_only(p)) for v, p in payloads]
    verdict_counts: dict[str, int] = {}
    for expected, ar in async_results:
        resp = wait_result(ar, timeout=RESULT_TIMEOUT)
        actual = resp.get("result", "?")
        verdict_counts[actual] = verdict_counts.get(actual, 0) + 1
    duration = round(time.monotonic() - t0, 2)

    result = {
        "duration_sec": duration, "total": sum(verdict_counts.values()),
        "verdicts": verdict_counts,
    }
    print(f"    {duration}s, verdicts={verdict_counts}")
    return result


# ── Test 4: 判题模式对比（仅 C++） ──


def run_judge_mode(mode: str, count: int, lang_cfg: dict, extra: dict | None) -> dict:
    """运行指定判题模式的 AC 任务，测量吞吐和延迟。"""
    print(f"  [{mode}] sending {count} AC tasks...")
    payloads = []
    for i in range(count):
        sid = f"bench-{mode}-{i}-{uuid.uuid4().hex[:6]}"
        is_spj = "SPJ" in mode
        is_interactive = "INTERACTIVE" in mode
        is_python = "Python" in mode

        if is_spj:
            source = SOURCE_CPP_SPJ_AC if not is_python else "print('ACCEPT')"
            tc = {"case_no": 1, "points": 100.0, "time_limit_ms": 2000,
                  "memory_limit_kb": 262144, "input_inline": "",
                  "output_inline": None}
        elif is_interactive:
            source = USER_INT_AC if not is_python else USER_INT_PY_AC
            tc = {"case_no": 1, "points": 100.0, "time_limit_ms": 2000,
                  "memory_limit_kb": 262144, "input_inline": "x\n",
                  "output_inline": "x\n"}
        else:  # STANDARD
            is_python = "Python" in mode
            source = SOURCE_CPP_ECHO if not is_python else SOURCE_PY_ECHO
            tc = {"case_no": 1, "points": 100.0, "time_limit_ms": 2000,
                  "memory_limit_kb": 262144, "input_inline": "x\n",
                  "output_inline": "x\n"}

        p = build_payload(sid, "SPJ" if is_spj else ("INTERACTIVE" if is_interactive else "STANDARD"),
                          source, lang_cfg, [tc])
        if extra:
            p.update(extra)
        payloads.append(p)

    latencies: list[float] = []
    verdicts: list[str] = []
    async_results = []

    for p in payloads:
        async_results.append(send_only(p))

    t0 = time.monotonic()
    for ar in async_results:
        t1 = time.monotonic()
        resp = wait_result(ar, timeout=RESULT_TIMEOUT + 10)
        t2 = time.monotonic()
        latencies.append((t2 - t1) * 1000)
        verdicts.append(resp.get("result", "?"))
    duration = time.monotonic() - t0

    success = sum(1 for v in verdicts if v == "AC")

    result = {
        "total": count, "success": success, "failed": count - success,
        "duration_sec": duration,
        "throughput_req_per_sec": round(count / max(duration, 0.01), 2),
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1),
    }
    print(f"    {result['throughput_req_per_sec']} req/s, "
          f"P50={result['latency_p50_ms']} P95={result['latency_p95_ms']}ms, "
          f"success={success}/{count}")
    return result


# ── Main ──


def main():
    t_all = time.monotonic()
    print("=" * 60)
    print("acoj-worker 性能基准测试")
    print("=" * 60)

    results = {"meta": {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "burst_count": BURST_COUNT,
        "sustained_threads": SUSTAINED_THREADS,
        "sustained_duration_sec": SUSTAINED_DURATION,
    }}

    for lang_name, (lang_cfg, sources) in LANGUAGES.items():
        print(f"\n{'─'*60}")
        print(f"语言: {lang_name}")
        print(f"{'─'*60}")
        try:
            binfo = run_burst_ac(lang_name, lang_cfg, sources)
            sinfo = run_sustained(lang_name, lang_cfg, sources)
            minfo = run_mixed(lang_name, lang_cfg, sources)
            results[lang_name] = {"burst_ac": binfo, "sustained": sinfo, "mixed": minfo}
        except Exception as e:
            print(f"  [!] 测试失败: {e}")
            results[lang_name] = {"error": str(e)}

    # Judge mode comparison: STANDARD / SPJ(C++/Python) / INTERACTIVE
    print(f"\n{"\u2500"*60}")
    print("判题模式对比")
    print(f"{"\u2500"*60}")
    mode_tests = [
        ("STANDARD(C++)", 16, LANG_CPP17, None),
        ("STANDARD(Python)", 16, LANG_PYTHON3, None),
        ("SPJ(C++)", 16, LANG_CPP17, SPJ_EXTRA.get("C++")),
        ("SPJ(Python)", 16, LANG_PYTHON3, SPJ_EXTRA.get("Python")),
        ("INTERACTIVE(C++)", 16, LANG_CPP17, INTERACTOR_EXTRA.get("C++")),
        ("INTERACTIVE(Python)", 16, LANG_PYTHON3, INTERACTOR_EXTRA.get("Python")),
    ]
    for label, cnt, cfg, extra in mode_tests:
        if extra is None and "STANDARD" not in label:
            print(f"  [{label}] skip (unsupported)")
            continue
        mode = "STANDARD" if "STANDARD" in label else ("SPJ" if "SPJ" in label else "INTERACTIVE")
        try:
            minfo = run_judge_mode(label, cnt, cfg, extra)
            results.setdefault("JudgeMode", {})[label] = minfo
        except Exception as e:
            print(f"  [{label}] failed: {e}")


    out_path = os.path.join(_project_root, "docs", "benchmark_result.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"结果写入 {out_path}")


if __name__ == "__main__":
    main()
