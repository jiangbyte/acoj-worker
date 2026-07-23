"""交互判题模式集成测试 — 通过 Celery 发送，覆盖 AC/WA/RE 三种场景。

用法：
    python tests/test_interactive.py [ac|wa|re]
"""

import sys
import uuid

from judge_helper import (
    LANG_CPP17, build_payload, send_and_await,
)

# ── 交互器源码 ──────────────────────────────────────

INTERACTOR_SOURCE_AC = r"""#include <iostream>
#include <string>

int main() {
    std::cout << "Alice" << std::endl;
    std::string response;
    if (!std::getline(std::cin, response)) {
        std::cerr << "wrong answer: expected greeting from user, got EOF" << std::endl;
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

# ── 用户程序源码 ─────────────────────────────────────

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
    std::cout << "Hi, " << name << "!" << std::endl;
    return 0;
}
"""

USER_SOURCE_RE = r"""#include <iostream>

int main() {
    int* p = nullptr;
    *p = 42;
    return 0;
}
"""


def print_result(result: dict):
    if not result:
        print("[✗] 未收到结果")
        return
    print(f"[←] === 判题结果: {result.get('submission_id')} ===")
    print(f"    状态:   {result.get('status', 'N/A')}")
    print(f"    结果:   {result.get('result', 'N/A')}")
    print(f"    分数:   {result.get('score', 0):.1f}")
    print(f"    耗时:   {result.get('time_ms', 0)}ms")
    print(f"    内存:   {result.get('memory_kb', 0)}KB")
    for i, c in enumerate(result.get("cases", [])):
        print(f"    Case {c.get('case_no', i+1)}: {c.get('result', '?')}  "
              f"time={c.get('time_ms', 0)}ms  mem={c.get('memory_kb', 0)}KB  "
              f"score={c.get('points', 0):.1f}")
        if c.get("stderr_preview"):
            print(f"         stderr: {c['stderr_preview'][:200]}")
    if result.get("compile_output"):
        print(f"    编译输出: {result['compile_output'][:500]}")


def test_interactive_ac():
    sid = f"v-interactive-ac-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_SOURCE_AC, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE_AC,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    print_result(result)
    assert result.get("result") == "AC", f"预期 AC，实际 {result.get('result')}"
    assert result.get("score", 0) >= 100.0, f"预期 100 分，实际 {result.get('score')}"
    print("[✓] INTERACTIVE AC 测试通过\n")


def test_interactive_wa():
    sid = f"v-interactive-wa-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_SOURCE_WA, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE_AC,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
    result = send_and_await(sid, payload)
    print_result(result)
    assert result.get("result") == "WA", f"预期 WA，实际 {result.get('result')}"
    print("[✓] INTERACTIVE WA 测试通过\n")


def test_interactive_re():
    sid = f"v-interactive-re-{uuid.uuid4().hex[:6]}"
    payload = build_payload(sid, "INTERACTIVE", USER_SOURCE_RE, LANG_CPP17, [{
        "case_no": 1, "points": 100.0, "time_limit_ms": 2000, "memory_limit_kb": 262144,
        "input_inline": "", "output_inline": None,
    }], interactor={
        "language": LANG_CPP17, "source": INTERACTOR_SOURCE_AC,
        "time_limit_ms": 4000, "memory_limit_kb": 262144,
    })
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
