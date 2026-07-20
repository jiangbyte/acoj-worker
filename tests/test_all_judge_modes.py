"""全面判题模式集成测试 — 通过 MQ 直接发送判题请求。

覆盖 STANDARD(ACM/OI/IOI/CE)、SPECIAL_JUDGE、INTERACTIVE 全部模式。
打印完整请求数据和响应数据。

用法：
    python tests/test_all_judge_modes.py              # 全部
    python tests/test_all_judge_modes.py standard     # STANDARD 分组
    python tests/test_all_judge_modes.py spj          # SPJ 分组
    python tests/test_all_judge_modes.py interactive  # INTERACTIVE 分组

依赖：worker 必须已启动并连接 MQ；RabbitMQ 必须运行。
"""

import json
import os
import sys
import uuid
from typing import Any

import pika

# ── RabbitMQ 工具函数 ──────────────────────────────────

MQ_URL = os.environ.get("MQ__URL", "amqp://admin:123456@127.0.0.1:5672/%2F")
EXCHANGE = "oj.judge"


def send_and_await(submission_id: str, payload: dict, timeout: float = 30.0) -> dict:
    """发送 MQ 判题请求并等待结果。"""
    params = pika.URLParameters(MQ_URL)
    conn = pika.BlockingConnection(params)
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)

    print(f"\n{'='*70}")
    print(f"[→] 已发送请求: {submission_id}  mode={payload.get('judge_mode')}")
    print(f"{'='*70}")
    print(f"[请求数据]")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key="request",
        body=json.dumps(payload, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
    )

    result_queue = f"result.{submission_id}"
    channel.queue_declare(queue=result_queue, durable=False, auto_delete=True)
    channel.queue_bind(queue=result_queue, exchange=EXCHANGE, routing_key="result")

    result: dict = {}

    def on_message(_ch, _method, _properties, body):
        nonlocal result
        data = json.loads(body)
        if data.get("submission_id") == submission_id:
            result.update(data)
            _ch.stop_consuming()

    channel.basic_consume(queue=result_queue, on_message_callback=on_message, auto_ack=True)

    import threading
    timer = threading.Timer(timeout, channel.stop_consuming)
    timer.start()
    try:
        channel.start_consuming()
    finally:
        timer.cancel()
    conn.close()

    print(f"\n[响应数据]")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def assert_result(result: dict, expected_result: str, expected_score: float | None = None,
                  label: str = "") -> bool:
    actual = result.get("result")
    actual_score = result.get("score", 0)
    ok = actual == expected_result
    if expected_score is not None:
        ok = ok and abs(actual_score - expected_score) < 0.01

    status = "[PASS]" if ok else "[FAIL]"
    extra = f" score={actual_score}" if expected_score is not None else ""
    print(f"  {status} {label}: result={actual}{extra} (expected {expected_result})")
    return ok


# ── 语言配置 ──────────────────────────────────────────

LANG_CPP17 = {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "/usr/bin/g++ -std=c++17 -O2 -o {exe} {source}",
    "run_command": "{exe}",
}

# ── 源码 ─────────────────────────────────────────────

SOURCE_CPP_ECHO = r'''#include <iostream>
#include <string>
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::cout << line << std::endl;
    }
    return 0;
}
'''

SOURCE_CPP_WRONG = r'''#include <iostream>
int main() {
    std::cout << "wrong output" << std::endl;
    return 0;
}
'''

SOURCE_CPP_CE = r'''#include <iostream>
int main() {
    std::cout << "missing semicolon" << std::endl
    return 0;
}
'''

SPJ_CHECKER = r'''#include <iostream>
#include <fstream>
#include <string>
int main(int argc, char* argv[]) {
    if (argc < 3) return 3;
    std::ifstream user_out(argv[2]);
    if (!user_out) return 3;
    std::string line;
    while (user_out >> line) {
        if (line == "ACCEPT") {
            std::cerr << "ok" << std::endl;
            return 0;
        }
    }
    std::cerr << "wrong answer: ACCEPT not found" << std::endl;
    return 1;
}
'''

SOURCE_CPP_SPJ_AC = r'''#include <iostream>
int main() {
    std::cout << "ACCEPT" << std::endl;
    return 0;
}
'''

SOURCE_CPP_SPJ_WA = r'''#include <iostream>
int main() {
    std::cout << "REJECT" << std::endl;
    return 0;
}
'''

INTERACTOR_SOURCE = r'''#include <iostream>
#include <string>
int main() {
    std::cout << "Alice" << std::endl;
    std::string response;
    if (!std::getline(std::cin, response)) {
        std::cerr << "wrong answer: got EOF" << std::endl;
        return 1;
    }
    if (response != "Hello, Alice!") {
        std::cerr << "wrong answer expected 'Hello, Alice!' found '" << response << "'" << std::endl;
        return 1;
    }
    std::cerr << "ok" << std::endl;
    return 0;
}
'''

USER_INT_AC = r'''#include <iostream>
#include <string>
int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hello, " << name << "!" << std::endl;
    return 0;
}
'''

USER_INT_WA = r'''#include <iostream>
#include <string>
int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hi, " << name << "!" << std::endl;
    return 0;
}
'''

USER_INT_RE = r'''#include <iostream>
int main() {
    int* p = nullptr;
    *p = 42;
    return 0;
}
'''


# ── 请求构建辅助 ─────────────────────────────────────

def build_payload(sid: str, judge_mode: str, source: str, language: dict | None,
                  test_cases: list[dict], **extra) -> dict:
    payload = {
        "submission_id": sid,
        "judge_mode": judge_mode,
        "problem": {
            "code": "v-test", "time_limit_ms": 2000,
            "memory_limit_kb": 262144, "points": 100.0, "partial": False,
        },
        "source": source,
        "test_cases": test_cases,
    }
    if language:
        payload["language"] = language
    payload.update(extra)
    return payload


# ── 测试函数 ─────────────────────────────────────────

def test_standard_acm_single_ac() -> bool:
    """STANDARD ACM: 单测点 AC"""
    sid = f"v-std-acm-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_ECHO, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "hello world\n", "output_inline": "hello world\n",
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "STANDARD ACM single AC")


def test_standard_acm_single_wa() -> bool:
    """STANDARD ACM: 单测点 WA"""
    sid = f"v-std-acm-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": "expected output\n",
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 0.0, "STANDARD ACM single WA")


def test_standard_acm_stop_on_first() -> bool:
    """STANDARD ACM: 首错即停 — 第1个AC, 第2个WA, 第3个应SKIPPED"""
    sid = f"v-std-acm-stop-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "STANDARD", SOURCE_CPP_WRONG, LANG_CPP17, [
        {"case_no": 1, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": "wrong output\n", "input_file": None, "output_file": None,
         "batch_no": None, "batch_depends": []},
        {"case_no": 2, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": "expected\n", "input_file": None, "output_file": None,
         "batch_no": None, "batch_depends": []},
        {"case_no": 3, "points": 33.34, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "", "output_inline": "", "input_file": None, "output_file": None,
         "batch_no": None, "batch_depends": []},
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
         "input_inline": "a\n", "output_inline": "a\n", "batch_no": None, "batch_depends": []},
        {"case_no": 2, "points": 33.33, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "b\n", "output_inline": "b\n", "batch_no": None, "batch_depends": []},
        {"case_no": 3, "points": 33.34, "time_limit_ms": 2000, "memory_limit_kb": 262144,
         "input_inline": "c\n", "output_inline": "wrong\n", "batch_no": None, "batch_depends": []},
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
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
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
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }])
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "STANDARD inline data AC")


def test_spj_ac() -> bool:
    """SPJ: checker 返回 AC"""
    sid = f"v-spj-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER})
    result = send_and_await(sid, payload)
    return assert_result(result, "AC", 100.0, "SPJ AC")


def test_spj_wa() -> bool:
    """SPJ: checker 返回 WA"""
    sid = f"v-spj-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "SPECIAL_JUDGE", SOURCE_CPP_SPJ_WA, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }], spj={"language": LANG_CPP17, "source": SPJ_CHECKER})
    result = send_and_await(sid, payload)
    return assert_result(result, "WA", 0.0, "SPJ WA")


def test_interactive_ac() -> bool:
    """INTERACTIVE: 用户正确回复 → AC"""
    sid = f"v-int-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_INT_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
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
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
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
        "input_file": None, "output_file": None, "batch_no": None, "batch_depends": [],
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    return assert_result(result, "RE", 0.0, "INTERACTIVE RE")


# ── 运行入口 ─────────────────────────────────────────

ALL_TESTS = {
    "acm_ac": test_standard_acm_single_ac,
    "acm_wa": test_standard_acm_single_wa,
    "acm_stop": test_standard_acm_stop_on_first,
    "oi": test_standard_oi_partial,
    "ioi": test_standard_ioi_batch_depends,
    "ce": test_standard_ce,
    "inline": test_standard_inline_data,
    "spj_ac": test_spj_ac,
    "spj_wa": test_spj_wa,
    "int_ac": test_interactive_ac,
    "int_wa": test_interactive_wa,
    "int_re": test_interactive_re,
}

GROUPS = {
    "standard": ["acm_ac", "acm_wa", "acm_stop", "oi", "ioi", "ce", "inline"],
    "spj": ["spj_ac", "spj_wa"],
    "interactive": ["int_ac", "int_wa", "int_re"],
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
