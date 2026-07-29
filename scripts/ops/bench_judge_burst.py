#!/usr/bin/env python3
"""Burst bench: fire N judge.execute tasks and measure wall / throughput.

Waits are sequential on purpose: Redis result backend + many concurrent
AsyncResult.get() can corrupt framing; wall-clock still reflects true
parallel execution on the worker side.

Usage:
  cd acoj-worker
  python scripts/ops/bench_judge_burst.py
  python scripts/ops/bench_judge_burst.py 100
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from tests.judge_helper import LANG_PYTHON3, build_payload, send_only, wait_result


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    src = 'import sys\nprint(sys.stdin.read(), end="")\n'
    payloads = []
    for i in range(n):
        sid = f"burst-{uuid.uuid4().hex[:10]}-{i}"
        payloads.append(
            build_payload(
                sid,
                "STANDARD",
                src,
                LANG_PYTHON3,
                [
                    {
                        "case_no": 1,
                        "points": 100.0,
                        "time_limit_ms": 1000,
                        "memory_limit_kb": 65536,
                        "input_inline": f"{i}\n",
                        "output_inline": f"{i}\n",
                    }
                ],
            )
        )

    print(f"dispatching {n} tasks ...")
    t0 = time.perf_counter()
    async_results = [send_only(p) for p in payloads]
    print(f"dispatch_wall_ms={(time.perf_counter() - t0) * 1000:.1f}")

    ok = 0
    fail = 0
    for ar in async_results:
        result = wait_result(ar, timeout=120)
        if result.get("result") == "AC" and result.get("status") == "COMPLETED":
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                print(
                    "fail sample",
                    result.get("result"),
                    result.get("error"),
                    result.get("status"),
                )

    total = time.perf_counter() - t0
    print(
        f"n={n} ok={ok} fail={fail} "
        f"total_wall_ms={total * 1000:.1f} "
        f"amortized_ms_per_task={total * 1000 / n:.1f} "
        f"throughput_qps={n / total:.2f}"
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
