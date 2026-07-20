"""交互判题模式集成测试。

发送 MQ 消息触发 worker 执行 INTERACTIVE 判题，验证结果。
需要 worker 已启动并连接 MQ。

用法：
    python tests/test_interactive.py [ac|wa]
"""

import json
import os
import sys
import uuid
from pathlib import Path

import pika

# ── 交互器源码（C++ testlib 风格） ──────────────────────────

# AC: 写名字 → 读问候 → 验证格式
INTERACTOR_SOURCE_AC = r"""#include <iostream>
#include <string>

int main() {
    // 1. 写名字到用户程序
    std::cout << "Alice" << std::endl;
    // 2. 读用户程序的问候
    std::string response;
    if (!std::getline(std::cin, response)) {
        std::cerr << "wrong answer: expected greeting from user, got EOF" << std::endl;
        return 1;
    }
    // 3. 验证问候格式
    if (response != "Hello, Alice!") {
        std::cerr << "wrong answer expected 'Hello, Alice!' found '" << response << "'" << std::endl;
        return 1;
    }
    std::cerr << "ok" << std::endl;
    return 0;
}
"""

INTERACTOR_SOURCE_WA = r"""#include <iostream>
#include <string>

int main() {
    std::cout << "Bob" << std::endl;
    std::string response;
    if (!std::getline(std::cin, response)) {
        std::cerr << "wrong answer: expected greeting, got EOF" << std::endl;
        return 1;
    }
    if (response != "Hello, Bob!") {
        std::cerr << "wrong answer expected 'Hello, Bob!' found '" << response << "'" << std::endl;
        return 1;
    }
    std::cerr << "ok" << std::endl;
    return 0;
}
"""

INTERACTOR_SOURCE_TIMEOUT = r"""#include <iostream>
#include <string>

int main() {
    // 不发送任何内容，也不读取 — 用户程序可能阻塞在读取交互器的输出上
    std::cerr << "interactor timed out" << std::endl;
    return 1;
}
"""

# ── 用户程序源码 ─────────────────────────────────────────

USER_SOURCE_AC = r"""#include <iostream>
#include <string>

int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hello, " << name << "!" << std::endl;
    return 0;
}
"""

USER_SOURCE_WA = r"""#include <iostream>
#include <string>

int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hi, " << name << "!" << std::endl;  // "Hi" instead of "Hello"
    return 0;
}
"""

USER_SOURCE_RE = r"""#include <iostream>

int main() {
    // 立即崩溃
    int* p = nullptr;
    *p = 42;
    return 0;
}
"""

# ── 语言配置（与 worker .env 对齐） ────────────────────

LANGUAGE_CPP17 = {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "/usr/bin/g++ -std=c++17 -O2 -o {exe} {source}",
    "run_command": "{exe}",
}


def build_judge_request(
    submission_id: str,
    judge_mode: str,
    source: str,
    language: dict,
    interactor: dict | None = None,
) -> dict:
    """构建与 service_portal._build_judge_request() 一致的 JudgeRequest"""
    return {
        "submission_id": submission_id,
        "judge_mode": judge_mode,
        "problem": {
            "code": "v-interactive-demo",
            "time_limit_ms": 2000,
            "memory_limit_kb": 262144,
            "points": 100.0,
            "partial": False,
        },
        "language": language,
        "source": source,
        "test_cases": [
            {
                "case_no": 1,
                "points": 100.0,
                "time_limit_ms": 2000,
                "memory_limit_kb": 262144,
                "input_file": None,
                "output_file": None,
                "input_inline": "",
                "output_inline": None,
                "batch_no": None,
                "batch_depends": [],
            },
        ],
        "interactor": interactor,
    }


def send_and_await(submission_id: str, payload: dict) -> dict:
    """发送 MQ 消息并等待、打印结果"""
    # RabbitMQ 连接参数
    mq_url = os.environ.get("MQ__URL", "amqp://admin:123456@127.0.0.1:5672/%2F")
    params = pika.URLParameters(mq_url)
    conn = pika.BlockingConnection(params)
    channel = conn.channel()

    exchange = "oj.judge"
    channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)

    # 发布判题请求
    channel.basic_publish(
        exchange=exchange,
        routing_key="request",
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
        ),
    )
    print(f"[→] 已发送请求: {submission_id}")

    # 声明回调队列并消费
    result_queue = f"result.{submission_id}"
    channel.queue_declare(queue=result_queue, durable=False, auto_delete=True)
    channel.queue_bind(queue=result_queue, exchange=exchange, routing_key="result")

    result: dict = {}

    def on_message(_ch, _method, _properties, body):
        nonlocal result
        data = json.loads(body)
        if data.get("submission_id") == submission_id:
            result.update(data)
            _ch.stop_consuming()

    channel.basic_consume(queue=result_queue, on_message_callback=on_message, auto_ack=True)

    import threading
    timer = threading.Timer(30.0, channel.stop_consuming)
    timer.start()
    try:
        channel.start_consuming()
    finally:
        timer.cancel()
    conn.close()
    return result


def print_result(result: dict):
    """格式化打印判题结果"""
    if not result:
        print("[✗] 未收到结果")
        return
    print(f"[←] === 判题结果: {result.get('submission_id')} ===")
    print(f"    模式:   INTERACTIVE")
    print(f"    状态:   {result.get('status', 'N/A')}")
    print(f"    结果:   {result.get('result', 'N/A')}")
    print(f"    分数:   {result.get('score', 0):.1f}")
    print(f"    耗时:   {result.get('time_ms', 0)}ms")
    print(f"    内存:   {result.get('memory_kb', 0)}KB")
    print(f"    编译错: {result.get('compile_error', False)}")
    print(f"    错误:   {result.get('error', 'None')}")

    for i, c in enumerate(result.get("cases", [])):
        print(f"    Case {c.get('case_no', i+1)}: {c.get('result', '?')}  "
              f"time={c.get('time_ms', 0)}ms  mem={c.get('memory_kb', 0)}KB  "
              f"score={c.get('points', 0):.1f}/{c.get('total', 0):.1f}")
        if c.get("stderr_preview"):
            print(f"         stderr: {c['stderr_preview'][:200]}")

    if result.get("compile_output"):
        out = result["compile_output"][:500]
        print(f"    编译输出: {out}")


def test_interactive_ac():
    """AC 场景：用户程序正确回复交互器"""
    sid = f"v-interactive-ac-{uuid.uuid4().hex[:6]}"
    payload = build_judge_request(
        submission_id=sid,
        judge_mode="INTERACTIVE",
        source=USER_SOURCE_AC,
        language=LANGUAGE_CPP17,
        interactor={
            "language": LANGUAGE_CPP17,
            "source": INTERACTOR_SOURCE_AC,
            "time_limit_ms": 4000,
            "memory_limit_kb": 262144,
        },
    )
    result = send_and_await(sid, payload)
    print_result(result)
    assert result.get("result") == "AC", f"预期 AC，实际 {result.get('result')}"
    assert result.get("score", 0) >= 100.0, f"预期 100 分，实际 {result.get('score')}"
    print("[✓] INTERACTIVE AC 测试通过\n")


def test_interactive_wa():
    """WA 场景：用户程序输出错误格式，交互器拒绝"""
    sid = f"v-interactive-wa-{uuid.uuid4().hex[:6]}"
    payload = build_judge_request(
        submission_id=sid,
        judge_mode="INTERACTIVE",
        source=USER_SOURCE_WA,
        language=LANGUAGE_CPP17,
        interactor={
            "language": LANGUAGE_CPP17,
            "source": INTERACTOR_SOURCE_AC,
            "time_limit_ms": 4000,
            "memory_limit_kb": 262144,
        },
    )
    result = send_and_await(sid, payload)
    print_result(result)
    assert result.get("result") == "WA", f"预期 WA，实际 {result.get('result')}"
    print("[✓] INTERACTIVE WA 测试通过\n")


def test_interactive_re():
    """RE 场景：用户程序崩溃"""
    sid = f"v-interactive-re-{uuid.uuid4().hex[:6]}"
    payload = build_judge_request(
        submission_id=sid,
        judge_mode="INTERACTIVE",
        source=USER_SOURCE_RE,
        language=LANGUAGE_CPP17,
        interactor={
            "language": LANGUAGE_CPP17,
            "source": INTERACTOR_SOURCE_AC,
            "time_limit_ms": 4000,
            "memory_limit_kb": 262144,
        },
    )
    result = send_and_await(sid, payload)
    print_result(result)
    cases = result.get("cases", [])
    assert cases, "应有至少一个 case"
    assert cases[0].get("result") == "RE", f"预期 RE，实际 {cases[0].get('result')}"
    print("[✓] INTERACTIVE RE 测试通过\n")


if __name__ == "__main__":
    test_map = {
        "ac": test_interactive_ac,
        "wa": test_interactive_wa,
        "re": test_interactive_re,
        "all": lambda: [test_interactive_ac(), test_interactive_wa(), test_interactive_re()],
    }

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    fn = test_map.get(target)
    if fn is None:
        print(f"未知测试: {target}, 可选: ac, wa, re, all")
        sys.exit(1)
    fn()
    print("全部测试完成")
