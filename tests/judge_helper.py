"""判题测试工具 — 经 Celery/Redis broker 发送，经 Redis result backend AsyncResult.get() 取回结果。"""

import json
import os
import sys
import time
import uuid
from typing import Any

# 确保项目根目录在 sys.path 中（测试脚本通常从 project root 运行）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.platform.tasks.celery_app import celery_app

# ── 结果通道 ──

# 判题结果超时（秒）
RESULT_TIMEOUT = 15.0


def send_and_await(submission_id: str, payload: dict, timeout: float = RESULT_TIMEOUT) -> dict:
    """通过 Celery 发送判题请求并等待结果。"""
    result = send_only(payload)
    return wait_result(result, submission_id, timeout)


def send_only(payload: dict) -> Any:
    """发送判题请求，不等待结果。返回 AsyncResult 供后续 wait_result()。

    使用场景（并发测试）：
        results = [send_only(p) for p in payloads]
        for r in results:
            wait_result(r)
    """
    return celery_app.send_task("judge.execute", args=[payload], queue="judge")


def wait_result(
    result: Any,
    label: str = "",
    timeout: float = RESULT_TIMEOUT,
) -> dict:
    """等待之前通过 send_only() 发出的判题结果。"""
    if label:
        print(f"\n[→] 等待结果: {label}")
    response: dict
    last_exc: Exception | None = None
    # Concurrent AsyncResult.get() against Redis backend can hit protocol framing
    # errors; retry with a fresh handle / short backoff.
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            response = {"error": str(last_exc) if last_exc else "timeout"}
            break
        try:
            response = result.get(timeout=max(0.1, remaining))
            break
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if "Protocol Error" in msg or "ConnectionError" in type(exc).__name__:
                time.sleep(0.05)
                try:
                    from app.platform.tasks.celery_app import celery_app

                    result = celery_app.AsyncResult(result.id)
                except Exception:
                    pass
                continue
            response = {"error": msg}
            break
    if label:
        print(f"[←] 结果: {response.get('result', '?')}")
    return response


def send_raw(body: str) -> dict:
    """发送判题请求（原始 body 格式），直接走 Celery task。

    boundary 测试使用：即使 payload 非法也能通过 task 报错拿到结果。
    """
    import json
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        payload = {"submission_id": f"raw-{uuid.uuid4().hex[:8]}", "body": body}

    return send_and_await(
        payload.get("submission_id", "?"), payload, timeout=RESULT_TIMEOUT
    )


# ── 断言 ──


def assert_result(
    result: dict,
    expected_result: str,
    expected_score: float | None = None,
    label: str = "",
) -> bool:
    actual = result.get("result")
    actual_score = result.get("score", 0)
    ok = actual == expected_result
    if expected_score is not None:
        ok = ok and abs(actual_score - expected_score) < 0.01

    status = "[PASS]" if ok else "[FAIL]"
    extra = f" score={actual_score}" if expected_score is not None else ""
    print(f"  {status} {label}: result={actual}{extra} (expected {expected_result})")
    return ok


# ── 语言配置 ──

LANG_CPP17 = {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "/usr/bin/g++ -std=c++17 -O2 -o {exe} {source}",
    "run_command": "{exe}",
}

LANG_PYTHON3 = {
    "key": "python3",
    "name": "Python 3",
    "extension": ".py",
    "compile_command": "",
    "run_command": "/usr/bin/python3 {source}",
}

# ── 源码 ──

SOURCE_CPP_ECHO = r"""#include <iostream>
#include <string>
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::cout << line << std::endl;
    }
    return 0;
}
"""

SOURCE_CPP_WRONG = r"""#include <iostream>
int main() {
    std::cout << "wrong output" << std::endl;
    return 0;
}
"""

SOURCE_CPP_CE = r"""#include <iostream>
int main() {
    std::cout << "missing semicolon" << std::endl
    return 0;
}
"""

SPJ_CHECKER = r"""#include <iostream>
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
"""

SOURCE_CPP_SPJ_AC = r"""#include <iostream>
int main() {
    std::cout << "ACCEPT" << std::endl;
    return 0;
}
"""

SOURCE_CPP_SPJ_WA = r"""#include <iostream>
int main() {
    std::cout << "REJECT" << std::endl;
    return 0;
}
"""

SOURCE_CPP_TLE = r"""#include <iostream>
int main() {
    while (true) {}
    return 0;
}
"""

SOURCE_CPP_MLE = r"""#include <iostream>
#include <vector>
int main() {
    std::vector<char> v(200 * 1024 * 1024);
    for (size_t i = 0; i < v.size(); i += 4096) v[i] = 1;
    std::cout << (int)v[0] << std::endl;
    return 0;
}
"""

SOURCE_CPP_OLE = r"""#include <iostream>
int main() {
    while (true) {
        std::cout << "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n";
    }
    return 0;
}
"""

SOURCE_CPP_RE = r"""#include <iostream>
int main() {
    int* p = nullptr;
    *p = 42;
    return 0;
}
"""

SPJ_CHECKER_SIMPLE = r"""#include <iostream>
#include <fstream>
#include <string>
int main(int argc, char* argv[]) {
    if (argc < 4) return 3;
    std::ifstream output(argv[2]);
    std::ifstream answer(argv[3]);
    std::string o, a;
    output >> o;
    answer >> a;
    if (o == a) { std::cerr << "ok" << std::endl; return 0; }
    std::cerr << "wa" << std::endl; return 1;
}
"""

INTERACTOR_SOURCE = r"""#include <iostream>
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
"""

USER_INT_AC = r"""#include <iostream>
#include <string>
int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hello, " << name << "!" << std::endl;
    return 0;
}
"""

USER_INT_WA = r"""#include <iostream>
#include <string>
int main() {
    std::string name;
    std::getline(std::cin, name);
    std::cout << "Hi, " << name << "!" << std::endl;
    return 0;
}
"""

USER_INT_RE = r"""#include <iostream>
int main() {
    int* p = nullptr;
    *p = 42;
    return 0;
}
"""

# Python 交互判题用户程序（与 C++ INTERACTOR_SOURCE 协议一致）
USER_INT_PY_AC = """import sys
name = sys.stdin.readline().strip()
print("Hello, " + name + "!")
"""

USER_INT_PY_WA = """import sys
name = sys.stdin.readline().strip()
print("Hi, " + name + "!")
"""

# ── 请求构建辅助 ──


def build_payload(
    sid: str,
    judge_mode: str,
    source: str,
    language: dict | None,
    test_cases: list[dict],
    **extra,
) -> dict:
    """构建判题请求 payload。"""
    payload = {
        "submission_id": sid,
        "judge_mode": judge_mode,
        "problem": {
            "code": "v-test",
            "time_limit_ms": 2000,
            "memory_limit_kb": 262144,
            "points": 100.0,
            "partial": False,
        },
        "source": source,
        "test_cases": test_cases,
    }
    if language:
        payload["language"] = language
    payload.update(extra)
    return payload
