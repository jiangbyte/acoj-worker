"""真实 Celery 协议测试：无 mock。走 Redis broker + 本机 sandbox。

- apply：进程内真实判题（sandbox）
- send_task → AsyncResult.get：需 `-Q judge` worker（本模块 fixture 拉起）
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from app.modules.judge.schemas import JudgeResultOut
from app.modules.judge.tasks import execute_judge
from tests.judge_helper import LANG_PYTHON3, build_payload, send_and_await


def _python_echo_payload(sid: str, inp: str, out: str, *, wrong: bool = False) -> dict:
    src = (
        'print("nope")\n'
        if wrong
        else 'import sys\nprint(sys.stdin.read(), end="")\n'
    )
    return build_payload(
        sid,
        "STANDARD",
        src,
        LANG_PYTHON3,
        [
            {
                "case_no": 1,
                "points": 100.0,
                "time_limit_ms": 2000,
                "memory_limit_kb": 65536,
                "input_inline": inp,
                "output_inline": out,
            }
        ],
    )


@pytest.fixture(scope="module")
def judge_queue_worker():
    """拉起消费 judge 队列的 Celery worker（现网 default worker 不消费 judge）。"""
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.worker.main:celery_app",
            "worker",
            "--without-mingle",
            "--without-gossip",
            "--pool",
            "solo",
            "--concurrency",
            "1",
            "-Q",
            "judge",
            "--loglevel",
            "WARNING",
            "-n",
            f"judge-it-{uuid.uuid4().hex[:8]}@%h",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Remote control is disabled; wait until the process stays up after broker connect.
    deadline = time.time() + 20
    ready_since: float | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail("judge celery worker exited early")
        if ready_since is None:
            ready_since = time.time()
        elif time.time() - ready_since >= 2.0:
            break
        time.sleep(0.2)
    else:
        proc.terminate()
        proc.wait(timeout=10)
        pytest.fail("judge celery worker did not stay ready")
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_apply_real_ac():
    """进程内 Celery apply：真实 sandbox 判 AC。"""
    sid = f"it-apply-ac-{uuid.uuid4().hex[:8]}"
    payload = _python_echo_payload(sid, "hello\n", "hello\n")
    out = execute_judge.apply(args=[payload]).get(timeout=60)
    parsed = JudgeResultOut.model_validate(out)
    assert parsed.status == "COMPLETED"
    assert parsed.result == "AC"
    assert parsed.score == 100.0
    assert parsed.cases[0].case_no == 1


def test_apply_real_wa():
    sid = f"it-apply-wa-{uuid.uuid4().hex[:8]}"
    payload = _python_echo_payload(sid, "hello\n", "hello\n", wrong=True)
    out = execute_judge.apply(args=[payload]).get(timeout=60)
    parsed = JudgeResultOut.model_validate(out)
    assert parsed.status == "COMPLETED"
    assert parsed.result == "WA"


def test_apply_invalid_payload_failed():
    out = execute_judge.apply(args=[{"submission_id": "bad-only"}]).get(timeout=30)
    parsed = JudgeResultOut.model_validate(out)
    assert parsed.status == "FAILED"
    assert parsed.error and "invalid payload" in parsed.error


def test_celery_send_and_async_result_consume(judge_queue_worker):
    """真实 broker：send_task(judge.execute) + AsyncResult.get 消费结果。"""
    _ = judge_queue_worker
    sid = f"it-celery-ac-{uuid.uuid4().hex[:8]}"
    payload = _python_echo_payload(sid, "ping\n", "ping\n")
    got = send_and_await(sid, payload, timeout=60)
    parsed = JudgeResultOut.model_validate(got)
    assert parsed.submission_id == sid
    assert parsed.status == "COMPLETED"
    assert parsed.result == "AC"


def test_celery_send_cpp_ac_against_running_worker():
    """依赖本机已启动 -Q judge 的 worker（不另起 fixture）。"""
    from tests.judge_helper import LANG_CPP17, SOURCE_CPP_ECHO

    sid = f"it-celery-cpp-{uuid.uuid4().hex[:8]}"
    payload = build_payload(
        sid,
        "STANDARD",
        SOURCE_CPP_ECHO,
        LANG_CPP17,
        [
            {
                "case_no": 1,
                "points": 100.0,
                "time_limit_ms": 2000,
                "memory_limit_kb": 65536,
                "input_inline": "hi\n",
                "output_inline": "hi\n",
            }
        ],
    )
    try:
        got = send_and_await(sid, payload, timeout=15)
    except Exception as exc:
        pytest.skip(f"no judge worker available: {exc}")
    parsed = JudgeResultOut.model_validate(got)
    assert parsed.status == "COMPLETED"
    assert parsed.result == "AC"
