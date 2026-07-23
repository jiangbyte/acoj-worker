"""Worker 异常边界测试。

C5: 重复 submission_id
C6: 无效 payload（缺必填字段、非法 JSON）
C7: 极端大源码（1MB）
"""

import json
import os
import sys
import uuid

from judge_helper import (
    LANG_CPP17, SOURCE_CPP_ECHO, build_payload, send_and_await, assert_result,
    send_raw,
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


# ── C5: 重复 submission_id ──────────────────────────

def test_c5_duplicate_id():
    """同一个 submission_id 发送两次，第2次不应崩溃"""
    print("\n[ C5 ] 重复 submission_id")
    sid = f"c5-dup-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "hello\n", "output_inline": "hello\n",
    }])

    r1 = send_and_await(sid, payload, timeout=15.0)
    ok1 = r1.get("result") == "AC"
    report("C5 first submission AC", ok1)

    r2 = send_and_await(sid, payload, timeout=15.0)
    ok2 = r2.get("result") == "AC"
    report("C5 duplicate submission AC (no crash)", ok2)

    import subprocess
    alive = subprocess.run(["pgrep", "-f", "celery.*worker"], capture_output=True).returncode == 0
    report("C5 worker still alive after duplicate", alive)


# ── C6: 无效 payload ────────────────────────────────

def test_c6_invalid_payload():
    """无效 payload 应被捕获，worker 不崩溃"""
    print("\n[ C6 ] 无效 payload")

    # 非法 JSON
    try:
        send_raw("this is not json")
        print("  [→] 非法 JSON 已发送")
    except Exception as e:
        print(f"  [→] 发送非法 JSON 异常: {e}")

    # 缺必填字段
    sid = f"c6-missing-{uuid.uuid4().hex[:6]}"
    try:
        send_raw(json.dumps({"submission_id": sid, "judge_mode": "STANDARD"}))
        print("  [→] 缺字段请求已发送")
    except Exception as e:
        print(f"  [→] 发送缺字段请求异常: {e}")

    # 未知 judge_mode
    sid = f"c6-unknown-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "UNKNOWN_MODE", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    r = send_and_await(sid, payload, timeout=10.0)
    ok = r.get("status") in ("COMPLETED",) and r.get("result") in ("AC", "FAILED")
    report("C6 unknown judge_mode", ok)

    import subprocess
    alive = subprocess.run(["pgrep", "-f", "celery.*worker"], capture_output=True).returncode == 0
    report("C6 worker still alive after invalid payload", alive)


# ── C7: 极端大源码 ──────────────────────────────────

def test_c7_huge_source():
    """1MB 源码应当能被正常处理"""
    print("\n[ C7 ] 极端大源码")

    padding = "// " + "x" * 1000 + "\n"
    big_comment = padding * 2000
    huge_source = f"""#include <iostream>
{big_comment}
int main() {{
    std::cout << "huge" << std::endl;
    return 0;
}}
"""
    print(f"  [→] 源码大小: {len(huge_source)} 字节")

    sid = f"c7-huge-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", huge_source, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 5000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "huge\n",
    }])
    r = send_and_await(sid, payload, timeout=60.0)
    ok = r.get("result") == "AC"
    report(f"C7 huge source ({len(huge_source)} bytes)", ok)

    import subprocess
    alive = subprocess.run(["pgrep", "-f", "celery.*worker"], capture_output=True).returncode == 0
    report("C7 worker still alive after huge source", alive)


if __name__ == "__main__":
    print("=" * 60)
    print("Worker 异常边界测试 (C5-C7)")
    print("=" * 60)

    test_c5_duplicate_id()
    test_c6_invalid_payload()
    test_c7_huge_source()

    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"结果: {PASS}/{total} 通过", end="")
    if FAIL:
        print(f", {FAIL} 失败")
    else:
        print()
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)
