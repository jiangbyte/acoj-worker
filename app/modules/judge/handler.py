"""判题消息处理器 — 接收 MQ 请求，读共享存储测试文件，执行 sandbox，发布结果。

支持判题模式：STANDARD(ACM/OI)、SPECIAL_JUDGE、INTERACTIVE。
计分策略：ACM（首错即停）、OI（逐点累加）、IOI（子任务全过给分）。
"""

import concurrent.futures
import json
import logging
import os
import shutil
import tempfile
import threading
import time as time_module
from collections import defaultdict
from pathlib import Path

from acoj_sandbox import DataRef, JudgeCase, JudgeLimits, SandboxClient, Status

from app.modules.judge.data_loader import (
    cleanup_remote_files,
    resolve_input_ref,
    resolve_output_ref,
)
from app.modules.judge.language_mapper import build_languages_config
from app.modules.judge.result_mapper import (
    SANDBOX_TO_OJ_RESULT,
    compute_overall_result,
    compute_score,
    to_oj_result,
)
from app.platform.mq.message import MQMessage
from app.platform.mq.producer import EventProducer

logger = logging.getLogger(__name__)

event_producer = EventProducer()


def handle_judge_request(message: MQMessage) -> None:
    """同步回调入口，由 MQConsumerWorker 调用。"""
    import asyncio

    payload = json.loads(message.body)
    asyncio.run(_process(payload))


def _check_output(actual_preview: str, expected_text: str | None) -> bool:
    """比对实际输出和预期输出，返回是否匹配。"""
    if expected_text is None:
        return True
    return actual_preview.strip() == expected_text.strip()


async def _process(payload: dict) -> None:
    """模式路由入口。"""
    judge_mode = payload.get("judge_mode", "STANDARD")
    t_start = time_module.monotonic()

    try:
        if judge_mode == "INTERACTIVE":
            result_payload = await _judge_interactive(payload)
        elif judge_mode == "SPECIAL_JUDGE":
            result_payload = await _judge_spj(payload)
        else:
            result_payload = await _judge_standard(payload)
    except Exception as exc:
        logger.exception("判题执行失败: %s", payload.get("submission_id"))
        result_payload = {
            "submission_id": payload["submission_id"],
            "status": "FAILED",
            "result": None,
            "score": 0.0,
            "time_ms": 0,
            "memory_kb": 0,
            "compile_output": None,
            "compile_error": False,
            "cases": [],
            "error": str(exc),
            "wall_time_ms": int((time_module.monotonic() - t_start) * 1000),
        }
    finally:
        cleanup_remote_files()

    result_payload["wall_time_ms"] = int((time_module.monotonic() - t_start) * 1000)
    await event_producer.publish(
        topic="result",
        payload=result_payload,
        exchange="oj.judge",
        exchange_type="direct",
    )
    logger.info("判题结果已发布: %s, result=%s", result_payload.get("submission_id"), result_payload.get("result"))


# ──────────────────────────────────────────────
# STANDARD 模式（ACM / OI / IOI）
# ──────────────────────────────────────────────

async def _judge_standard(payload: dict) -> dict:
    """STANDARD 判题 — 编译 + 执行 + 输出比对 + 计分。"""
    submission_id = payload["submission_id"]
    problem = payload["problem"]
    language_cfg = payload["language"]
    source = payload["source"]
    test_cases_data = payload["test_cases"]
    partial = problem.get("partial", False)
    t_start = time_module.monotonic()

    languages_config = build_languages_config(language_cfg)
    language_key = language_cfg["key"]

    cases = _build_judge_cases(test_cases_data, problem)
    if not cases:
        return _error_verdict(submission_id, "没有测试点数据")

    client = SandboxClient(languages=languages_config, transport="subprocess")
    try:
        batch_result = client.run_cases(
            language=language_key,
            source=source,
            cases=cases,
            stop_on_first_failure=False,
        )
    finally:
        client.close()

    has_ce = batch_result.compile.status != Status.AC

    raw_case_results: list[dict] = []
    stop_on_first = not partial and not any(tc.get("batch_no") for tc in test_cases_data)
    for i, case_result in enumerate(batch_result.cases):
        if stop_on_first and any(c["result"] != "AC" for c in raw_case_results):
            raw_case_results.append({
                "case_no": i + 1,
                "case_data": test_cases_data[i] if i < len(test_cases_data) else {},
                "result": "SKIPPED",
                "time_ms": 0, "memory_kb": 0,
                "points": 0, "total": 0,
                "stdout_preview": "", "stderr_preview": "",
            })
            continue

        tc_meta = test_cases_data[i] if i < len(test_cases_data) else {}
        sandbox_status = case_result.status
        run_ok = sandbox_status == Status.AC

        expected_text = _get_expected_text(case_result, tc_meta)
        output_match = run_ok and (not expected_text or _check_output(case_result.actual_output.preview_text, expected_text))
        oj_result = "AC" if (run_ok and output_match) else (to_oj_result(sandbox_status) if not run_ok else "WA")

        raw_case_results.append({
            "case_no": i + 1,
            "case_data": tc_meta,
            "result": oj_result,
            "time_ms": case_result.result.run.cpu_time_ms,
            "memory_kb": case_result.result.run.memory_bytes // 1024,
            "points": tc_meta.get("points", 0),
            "total": tc_meta.get("points", 0),
            "stdout_preview": case_result.actual_output.preview_text,
            "stderr_preview": case_result.stderr.preview_text,
        })

    if any(tc.get("batch_no") for tc in test_cases_data):
        case_results, score = _aggregate_batches(raw_case_results, test_cases_data)
    else:
        case_results = raw_case_results
        if has_ce:
            score = 0.0
        else:
            score = sum(c["points"] for c in case_results if c["result"] == "AC")

    overall_result = "CE" if has_ce else ("AC" if score >= problem["points"] else compute_overall_result(False, case_results))

    total_time = batch_result.total_cpu_time_ms
    peak_mem = batch_result.peak_memory_bytes // 1024

    return {
        "submission_id": submission_id,
        "status": "COMPLETED",
        "result": overall_result,
        "score": score,
        "time_ms": total_time,
        "memory_kb": peak_mem,
        "compile_output": batch_result.compile.message or batch_result.message,
        "compile_error": has_ce,
        "cases": case_results,
        "error": None,
    }


def _build_judge_cases(test_cases_data: list[dict], problem: dict) -> list[JudgeCase]:
    cases = []
    for tc in test_cases_data:
        case_limits = JudgeLimits(
            cpu_time_ms=tc.get("time_limit_ms") or problem["time_limit_ms"],
            real_time_ms=(tc.get("time_limit_ms") or problem["time_limit_ms"]) * 3,
            memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
            processes=256,
        )
        cases.append(
            JudgeCase(
                case_id=str(tc["case_no"]),
                input=resolve_input_ref(tc),
                expected_output=resolve_output_ref(tc),
                limits=case_limits,
            )
        )
    return cases


def _get_expected_text(case_result, tc_meta: dict) -> str:
    expected_ref = case_result.expected_output
    if expected_ref is not None and expected_ref.preview_text:
        return expected_ref.preview_text
    return tc_meta.get("output_inline") or ""


def _aggregate_batches(
    raw_case_results: list[dict],
    test_cases_data: list[dict],
) -> tuple[list[dict], float]:
    batch_ac: dict[int | None, bool] = {}
    for tc, cr in zip(test_cases_data, raw_case_results):
        bn = tc.get("batch_no")
        if bn is not None:
            prev = batch_ac.get(bn, True)
            batch_ac[bn] = prev and cr["result"] == "AC"

    for tc, cr in zip(test_cases_data, raw_case_results):
        bn = tc.get("batch_no")
        if bn is not None:
            deps = tc.get("batch_depends") or tc.get("batch_dependencies") or []
            for dep in deps:
                if dep in batch_ac and not batch_ac[dep]:
                    cr["result"] = "SKIPPED"
                    cr["points"] = 0.0

    batch_ac.clear()
    for tc, cr in zip(test_cases_data, raw_case_results):
        bn = tc.get("batch_no")
        if bn is not None:
            prev = batch_ac.get(bn, True)
            batch_ac[bn] = prev and cr["result"] == "AC"

    batches: dict[int | None, list[dict]] = defaultdict(list)
    batch_order: list[int | None] = []
    seen_batches: set[int | None] = set()

    for cr, tc in zip(raw_case_results, test_cases_data):
        bn = tc.get("batch_no")
        if bn not in seen_batches:
            seen_batches.add(bn)
            batch_order.append(bn)
        batches[bn].append(cr)

    case_results: list[dict] = []
    total_score = 0.0

    for bn in batch_order:
        batch_cases = batches[bn]
        all_ac = batch_ac.get(bn, True)

        if bn is None:
            for c in batch_cases:
                case_results.append(c)
                if c["result"] == "AC":
                    total_score += c["points"]
        else:
            if all_ac:
                batch_points = sum(c["points"] for c in batch_cases)
                for c in batch_cases:
                    case_results.append(dict(c))
                total_score += batch_points
            else:
                for c in batch_cases:
                    c_adj = dict(c)
                    c_adj["points"] = 0.0
                    case_results.append(c_adj)

    return case_results, total_score


# ──────────────────────────────────────────────
# SPJ 模式（Special Judge / Testlib Checker）
# ──────────────────────────────────────────────

async def _judge_spj(payload: dict) -> dict:
    submission_id = payload["submission_id"]
    problem = payload["problem"]
    language_cfg = payload["language"]
    source = payload["source"]
    spj_cfg = payload.get("spj", {})
    test_cases_data = payload["test_cases"]
    t_start = time_module.monotonic()

    if not spj_cfg.get("source"):
        return _error_verdict(submission_id, "缺少 SPJ checker 源码")

    languages_config = build_languages_config(language_cfg)
    language_key = language_cfg["key"]

    checker_lang = spj_cfg["language"]
    checker_languages = build_languages_config(checker_lang)
    checker_key = checker_lang["key"]

    client = SandboxClient(languages=languages_config, transport="subprocess")
    try:
        program = client.prepare_source(language=language_key, source=source)
        if not program.compiled:
            return _error_verdict(submission_id, f"用户程序编译失败: {program.compile.message}")

        checker_client = SandboxClient(languages=checker_languages, transport="subprocess")
        try:
            checker_program = checker_client.prepare_source(language=checker_key, source=spj_cfg["source"])
            if not checker_program.compiled:
                return _error_verdict(submission_id, f"SPJ checker 编译失败: {checker_program.compile.message}")
        finally:
            checker_client.close()

        all_cases: list[dict] = []
        all_ac = True
        total_score = 0.0
        per_case_points = problem["points"] / max(len(test_cases_data), 1)

        for i, tc in enumerate(test_cases_data):
            input_ref = resolve_input_ref(tc)
            expected_ref = resolve_output_ref(tc)

            case_limits = JudgeLimits(
                cpu_time_ms=tc.get("time_limit_ms") or problem["time_limit_ms"],
                real_time_ms=(tc.get("time_limit_ms") or problem["time_limit_ms"]) * 3,
                memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
                processes=256,
            )
            user_result = program.run(
                input_data=input_ref.data or "",
                input=input_ref,
                limits=case_limits,
            )
            user_ac = user_result.status == Status.AC

            from acoj_sandbox import testlib_checker_language

            checker_lang_full = testlib_checker_language(id=checker_key)
            spj_languages = type(checker_languages)([checker_lang_full])
            spj_client = SandboxClient(languages=spj_languages, transport="subprocess")
            try:
                spj_result = spj_client.run_testlib_checker(
                    checker_source=spj_cfg["source"],
                    input=DataRef.from_data(tc.get("input_inline", "")),
                    actual_output=DataRef.from_path(user_result.stdout_path),
                    expected_output=expected_ref or DataRef.from_data(""),
                )
            finally:
                spj_client.close()

            case_ac = user_ac and spj_result.accepted
            points = per_case_points if case_ac else 0.0
            if case_ac:
                total_score += points
            else:
                all_ac = False

            all_cases.append({
                "case_no": tc["case_no"],
                "result": "AC" if case_ac else "WA",
                "time_ms": user_result.run.cpu_time_ms,
                "memory_kb": user_result.run.memory_bytes // 1024,
                "points": points,
                "total": per_case_points,
                "stdout_preview": DataRef.from_path(user_result.stdout_path).preview_text,
                "stderr_preview": DataRef.from_path(user_result.stderr_path).preview_text,
            })

    finally:
        client.close()

    return {
        "submission_id": submission_id,
        "status": "COMPLETED",
        "result": "AC" if all_ac else "WA",
        "score": total_score,
        "time_ms": sum(c["time_ms"] for c in all_cases),
        "memory_kb": max(c["memory_kb"] for c in all_cases) if all_cases else 0,
        "compile_output": None,
        "compile_error": False,
        "cases": all_cases,
        "error": None,
    }


# ──────────────────────────────────────────────
# INTERACTIVE 模式
# ──────────────────────────────────────────────

async def _judge_interactive(payload: dict) -> dict:
    """交互判题 — 编译用户程序 + 编译交互器，通过 FIFO 管道双向通信。

    破死锁方案：在主线程用 os.open(fifo, os.O_RDWR) 不阻塞打开 FIFO，该 fd
    相当于同时持有读写端。后续子进程的 O_RDONLY/O_WRONLY 都不会阻塞。

    FIFO 方向：
      fifo_AB = user→interactor: user stdout, interactor stdin
      fifo_BA = interactor→user: interactor stdout, user stdin

    交互器通过 stderr 输出 judge message，通过 exit code 报告 verdict:
      exit=0 → AC, exit=1 → WA (exit_codes_ok=[0,1] 让 sandbox 接受这两个值)
    """
    submission_id = payload["submission_id"]
    problem = payload["problem"]
    interactor_cfg = payload.get("interactor", {})
    source = payload["source"]
    test_cases_data = payload["test_cases"]
    language_cfg = payload.get("language")

    if not interactor_cfg.get("source"):
        return _error_verdict(submission_id, "缺少交互器源码")

    languages_config = build_languages_config(language_cfg) if language_cfg else None
    language_key = language_cfg["key"] if language_cfg else None
    interactor_languages = build_languages_config(interactor_cfg["language"], exe_filename="interactor")
    interactor_key = interactor_cfg["language"]["key"]

    all_cases: list[dict] = []
    all_ac = True
    total_score = 0.0
    per_case_points = problem["points"] / max(len(test_cases_data), 1)

    for i, tc in enumerate(test_cases_data):
        input_ref = resolve_input_ref(tc)
        case_limits = JudgeLimits(
            cpu_time_ms=tc.get("time_limit_ms") or problem["time_limit_ms"],
            real_time_ms=(tc.get("time_limit_ms") or problem["time_limit_ms"]) * 5,
            memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
            processes=256,
        )

        work_dir = Path(tempfile.mkdtemp(prefix="acoj-interactive-"))
        input_file = work_dir / "input.txt"
        input_data = input_ref.data if isinstance(input_ref.data, (str, bytes)) else ""
        if isinstance(input_data, bytes):
            input_file.write_bytes(input_data)
        else:
            input_file.write_text(input_data, encoding="utf-8")

        fifo_AB = work_dir / "user_to_interactor.fifo"
        fifo_BA = work_dir / "interactor_to_user.fifo"
        os.mkfifo(fifo_AB)
        os.mkfifo(fifo_BA)

        fd_AB = os.open(str(fifo_AB), os.O_RDWR)
        fd_BA = os.open(str(fifo_BA), os.O_RDWR)

        user_client = SandboxClient(languages=languages_config, transport="subprocess") if languages_config else None
        interactor_client = SandboxClient(languages=interactor_languages, transport="subprocess")
        user_program = None
        interactor_program = None

        try:
            if user_client and source:
                user_program = user_client.prepare_source(
                    language=language_key,
                    source=source,
                    workspace=str(work_dir),
                )
                if not user_program.compiled:
                    all_cases.append({
                        "case_no": tc["case_no"], "result": "CE",
                        "time_ms": 0, "memory_kb": 0, "points": 0.0,
                        "total": per_case_points,
                        "stdout_preview": "", "stderr_preview": user_program.compile.message,
                    })
                    all_ac = False
                    continue

            interactor_program = interactor_client.prepare_source(
                language=interactor_key,
                source=interactor_cfg["source"],
                workspace=str(work_dir),
            )
            if not interactor_program.compiled:
                all_cases.append({
                    "case_no": tc["case_no"], "result": "IE",
                    "time_ms": 0, "memory_kb": 0, "points": 0.0,
                    "total": per_case_points,
                    "stdout_preview": "", "stderr_preview": interactor_program.compile.message,
                })
                all_ac = False
                continue

            holder: dict[str, object] = {"user": None, "interactor": None}
            interactor_stderr_path = work_dir / "interactor.stderr"

            def _try_run_user():
                if not user_program:
                    return None
                try:
                    return user_program.run_with_paths(
                        stdin_path=str(fifo_BA),
                        stdout_path=str(fifo_AB),
                        stderr_path=str(work_dir / "user.stderr"),
                        limits=case_limits,
                        capture_output=False,
                        allow_file_io=True,
                    )
                except Exception as exc:
                    logger.error("交互判题用户程序异常: %s", exc)
                    return None

            def _try_run_interactor():
                interactor_limits = JudgeLimits(
                    cpu_time_ms=interactor_cfg.get("time_limit_ms") or problem["time_limit_ms"] * 2,
                    real_time_ms=(interactor_cfg.get("time_limit_ms") or problem["time_limit_ms"] * 2) * 2,
                    memory_bytes=(interactor_cfg.get("memory_limit_kb") or problem["memory_limit_kb"]) * 1024,
                    processes=256,
                )
                try:
                    return interactor_program.run_with_paths(
                        stdin_path=str(fifo_AB),
                        stdout_path=str(fifo_BA),
                        stderr_path=str(interactor_stderr_path),
                        limits=interactor_limits,
                        capture_output=False,
                        variables={"input_file": str(input_file)},
                        allow_file_io=True,
                        exit_codes_ok=[0, 1],
                    )
                except Exception as exc:
                    logger.error("交互判题交互器异常: %s", exc)
                    return None

            timeout_seconds = max((problem["time_limit_ms"] * 5) / 1000.0, 10)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                user_fut = pool.submit(_try_run_user)
                interactor_fut = pool.submit(_try_run_interactor)
                try:
                    holder["user"] = user_fut.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    logger.warning("交互判题用户程序超时: case=%d, timeout=%.1fs", i + 1, timeout_seconds)
                try:
                    holder["interactor"] = interactor_fut.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    logger.warning("交互判题交互器超时: case=%d, timeout=%.1fs", i + 1, timeout_seconds)

            user_result = holder.get("user")
            interactor_result = holder.get("interactor")

            interactor_stderr_text = ""
            if interactor_stderr_path.exists():
                interactor_stderr_text = interactor_stderr_path.read_text(
                    encoding="utf-8", errors="replace",
                )[:4096]

            # 判定：用户 runtime 错误 > 交互器 runtime 错误 > WA > AC
            status_str = "SE"
            if user_result is not None and interactor_result is not None:
                if user_result.status != Status.AC:
                    status_str = to_oj_result(user_result.status)
                elif interactor_result.status != Status.AC:
                    status_str = to_oj_result(interactor_result.status)
                elif interactor_result.run.exit_code != 0:
                    status_str = "WA"
                else:
                    status_str = "AC"

            user_ac = status_str == "AC"
            points = per_case_points if user_ac else 0.0
            if user_ac:
                total_score += points
            else:
                all_ac = False

            time_ms = user_result.run.cpu_time_ms if user_result else 0
            mem_kb = user_result.run.memory_bytes // 1024 if user_result else 0

            all_cases.append({
                "case_no": tc["case_no"],
                "result": status_str,
                "time_ms": time_ms,
                "memory_kb": mem_kb,
                "points": points,
                "total": per_case_points,
                "stdout_preview": user_result.stdout[:2048] if user_result and user_result.stdout else "",
                "stderr_preview": interactor_stderr_text,
            })

        finally:
            os.close(fd_AB)
            os.close(fd_BA)
            if user_client:
                user_client.close()
            interactor_client.close()
            shutil.rmtree(work_dir, ignore_errors=True)

    non_ac = [c["result"] for c in all_cases if c["result"] not in ("AC", "SKIPPED")]
    overall_result = "AC" if all_ac else (non_ac[0] if non_ac else "WA")

    return {
        "submission_id": submission_id,
        "status": "COMPLETED",
        "result": overall_result,
        "score": total_score,
        "time_ms": sum(c["time_ms"] for c in all_cases),
        "memory_kb": max(c["memory_kb"] for c in all_cases) if all_cases else 0,
        "compile_output": None,
        "compile_error": False,
        "cases": all_cases,
        "error": None,
    }


# ──────────────────────────────────────────────
# 快捷构造结果
# ──────────────────────────────────────────────

def _error_verdict(submission_id: str, msg: str) -> dict:
    return {
        "submission_id": submission_id,
        "status": "FAILED",
        "result": None, "score": 0.0,
        "time_ms": 0, "memory_kb": 0,
        "compile_output": msg, "compile_error": False,
        "cases": [], "error": msg,
    }
