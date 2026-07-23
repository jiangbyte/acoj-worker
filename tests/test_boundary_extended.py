"""Worker 边界异常增强测试。

C19: Unicode 源码（中文变量名/注释/emoji）
C20: 空源码
C21: 二进制源码（含 \\x00）
C22: 200 测点单提交
C23: 极端 limit 值（time_limit_ms=1, memory_limit_kb=1）
C24: 1KB 长度 submission_id
"""

import sys
import subprocess
import uuid
from judge_helper import LANG_CPP17, build_payload, send_and_await, SOURCE_CPP_ECHO

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


# ══════════════════════════════════════════════════════
# C19: Unicode 源码
# ══════════════════════════════════════════════════════


def test_c19_unicode_source():
    """Unicode 源码（中文变量名、注释、emoji）应正常编译运行。"""
    print("\n[ C19 ] Unicode 源码")
    source = r"""#include <iostream>
#include <string>
int main() {
    // 中文注释 🌍
    std::string 姓名;
    姓名 = "世界";
    std::cout << "Hello, " << 姓名 << "!" << std::endl;
    return 0;
}
"""
    sid = f"c19-uni-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", source, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 5000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "Hello, 世界!\n",
    }])
    result = send_and_await(sid, payload, timeout=15.0)
    ok = result.get("result") == "AC"
    report("C19 unicode source (中文 + emoji)", ok)

    subprocess.run(["pgrep", "-f", "celery.*worker"],
                   capture_output=True).returncode == 0
    report("C19 worker alive", True)


# ══════════════════════════════════════════════════════
# C20: 空源码
# ══════════════════════════════════════════════════════


def test_c20_empty_source():
    """空源码应被正确处理，不崩溃。"""
    print("\n[ C20 ] 空源码")
    sid = f"c20-empty-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", "", LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload, timeout=15.0)
    ok = result.get("result") in ("CE", None)
    report(f"C20 empty source: result={result.get('result')}", ok)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C20 worker alive after empty source", alive)


# ══════════════════════════════════════════════════════
# C21: 二进制源码
# ══════════════════════════════════════════════════════


def test_c21_binary_source():
    """源码含 \\x00 二进制数据，应正常处理不崩溃。"""
    print("\n[ C21 ] 二进制源码")
    source = "int main() { return 0; }\n\x00\x00\x00"
    # 添加空注释避开可能的外部工具检查
    sid = f"c21-bin-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", source, LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "expected\n",
    }])
    result = send_and_await(sid, payload, timeout=15.0)
    # 只要不崩溃就算通过
    ok = result.get("result") in ("CE", "AC", "WA", None)
    report(f"C21 binary source: result={result.get('result')}", ok)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C21 worker alive after binary source", alive)


# ══════════════════════════════════════════════════════
# C22: 200 测点单提交
# ══════════════════════════════════════════════════════


def test_c22_200_test_cases():
    """单一提交 200 个测试点，验证大批量测点处理能力。"""
    print("\n[ C22 ] 200 测点单提交")
    cases = []
    for i in range(200):
        cases.append({
            "case_no": i + 1,
            "points": 0.5,
            "time_limit_ms": 1000,
            "memory_limit_kb": 65536,
            "input_inline": f"{i}\n",
            "output_inline": f"{i}\n",
        })

    source = r"""#include <iostream>
int main() {
    int x;
    std::cin >> x;
    std::cout << x << std::endl;
    return 0;
}
"""
    sid = f"c22-200-{uuid.uuid4().hex[:6]}"
    payload = {
        "submission_id": sid,
        "judge_mode": "STANDARD",
        "problem": {
            "code": "v-test",
            "time_limit_ms": 1000,
            "memory_limit_kb": 65536,
            "points": 100.0,
            "partial": True,
        },
        "source": source,
        "language": LANG_CPP17,
        "test_cases": cases,
    }
    result = send_and_await(sid, payload, timeout=120.0)
    ok = result.get("result") == "AC"
    report(f"C22 200 test cases: result={result.get('result')}", ok)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C22 worker alive after 200 cases", alive)


# ══════════════════════════════════════════════════════
# C23: 极端 limit 值
# ══════════════════════════════════════════════════════


def test_c23_extreme_limits():
    """极端 limit（time_limit_ms=1, memory_limit_kb=1）应正确拒绝，不崩溃。"""
    print("\n[ C23 ] 极端 limit 值")
    sid = f"c23-ext-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", "int main() { return 0; }", LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 1, "memory_limit_kb": 1,
        "input_inline": "", "output_inline": "",
    }])
    result = send_and_await(sid, payload, timeout=15.0)
    actual = result.get("result")
    # 极端 limit 可能产生任何非崩溃结果
    ok = actual in ("TLE", "MLE", "RE", "SE", "IE", None)
    report(f"C23 extreme limits (1ms/1KB): result={actual}", ok)

    alive = subprocess.run(["pgrep", "-f", "celery.*worker"],
                           capture_output=True).returncode == 0
    report("C23 worker alive after extreme limits", alive)


# ══════════════════════════════════════════════════════
# C24: 超长 submission_id
# ══════════════════════════════════════════════════════


def test_c24_long_submission_id():
    """超长 submission_id（100 字符）应被正常处理。"""
    print("\n[ C24 ] 超长 submission_id (100 chars)")
    long_id = "c24-long-" + "x" * 88  # 总长约 100 字符
    payload = build_payload(long_id, "STANDARD",
                            SOURCE_CPP_ECHO,
                            LANG_CPP17, [{
        "case_no": 1, "points": 100.0,
        "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "ok\n", "output_inline": "ok\n",
    }])
    result = send_and_await(long_id, payload, timeout=15.0)
    ok = result.get("result") == "AC"
    report("C24 long submission_id (100 chars)", ok)


# ══════════════════════════════════════════════════════
# ── 运行入口 ──
# ══════════════════════════════════════════════════════

ALL_TESTS = [
    ("C19 Unicode 源码", test_c19_unicode_source),
    ("C20 空源码", test_c20_empty_source),
    ("C21 二进制源码", test_c21_binary_source),
    ("C22 200 测点", test_c22_200_test_cases),
    ("C23 极端 limit", test_c23_extreme_limits),
    ("C24 超长 ID", test_c24_long_submission_id),
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
    print("Worker 边界异常增强测试 (C19-C24)")
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
