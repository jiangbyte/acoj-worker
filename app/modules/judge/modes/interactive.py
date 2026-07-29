"""INTERACTIVE 判题模式：用户程序 + 交互器通过 FIFO 双向通信。

死锁规避方案：
  主进程先以 O_RDWR 打开两端 FIFO，后续子进程的 O_RDONLY/O_WRONLY 不阻塞。

FIFO 方向：
  fifo_AB = user→interactor: user stdout, interactor stdin
  fifo_BA = interactor→user: interactor stdout, user stdin

交互器通过 stderr 输出 judge message，通过 exit code 报告 verdict:
  exit=0 → AC, exit=1 → WA (exit_codes_ok=[0,1] 让 sandbox 接受这两个值)

注：编译和 FIFO 运行必须在同一 workspace 下（sandbox 路径校验要求）。
编译缓存使多 case 场景下后续 case 的 prepare_source 仅复制缓存产物（~1ms）。
"""

import concurrent.futures
import logging
import os
import shutil
import tempfile
from pathlib import Path

from acoj_sandbox import JudgeLimits, SandboxClient, Status

from app.modules.judge.data_loader import resolve_input_ref
from app.modules.judge.language_config import build_languages_config
from app.modules.judge.modes.base import BaseJudgeMode
from app.modules.judge.result_mapper import to_oj_result
from app.modules.judge.sandbox_config import (
    build_cgroup_config,
    build_isolation_config,
    create_sandbox_client,
)
from app.modules.judge.metrics import (
    compile_metrics_from_process,
    reported_run_time_ms,
    run_metrics_from_cases,
)
from app.modules.judge.scoring import error_verdict

logger = logging.getLogger(__name__)


class InteractiveMode(BaseJudgeMode):
    """交互判题模式。"""

    def judge(self, payload: dict) -> dict:
        submission_id = payload["submission_id"]
        problem = payload["problem"]
        interactor_cfg = payload.get("interactor", {})
        source = payload["source"]
        test_cases_data = payload["test_cases"]
        language_cfg = payload.get("language")

        if not interactor_cfg.get("source"):
            return error_verdict(submission_id, "缺少交互器源码")

        languages_config = (
            build_languages_config(language_cfg) if language_cfg else None
        )
        language_key = language_cfg["key"] if language_cfg else None
        interactor_languages = build_languages_config(
            interactor_cfg["language"], exe_filename="interactor"
        )
        interactor_key = interactor_cfg["language"]["key"]

        isolation = build_isolation_config()
        cgroup = build_cgroup_config()

        all_cases: list[dict] = []
        all_ac = True
        total_score = 0.0
        per_case_points = problem["points"] / max(len(test_cases_data), 1)
        compile_time_ms = 0
        compile_memory_kb = 0

        for tc in test_cases_data:
            input_ref = resolve_input_ref(tc)
            case_limits = JudgeLimits(
                cpu_time_ms=tc.get("time_limit_ms") or problem["time_limit_ms"],
                real_time_ms=(tc.get("time_limit_ms") or problem["time_limit_ms"]) * 5,
                memory_bytes=(tc.get("memory_limit_kb") or problem["memory_limit_kb"])
                * 1024,
                processes=256,
                output_bytes=int(
                    tc.get("output_limit_bytes")
                    or problem.get("output_limit_bytes")
                    or (8 * 1024 * 1024)
                ),
            )

            work_dir = Path(tempfile.mkdtemp(prefix="acoj-interactive-"))
            input_file = work_dir / "input.txt"
            if input_ref.path:
                shutil.copyfile(input_ref.path, input_file)
            else:
                input_data = (
                    input_ref.data if isinstance(input_ref.data, (str, bytes)) else ""
                )
                if isinstance(input_data, bytes):
                    input_file.write_bytes(input_data)
                else:
                    input_file.write_text(input_data or "", encoding="utf-8")

            fifo_AB = work_dir / "user_to_interactor.fifo"
            fifo_BA = work_dir / "interactor_to_user.fifo"
            os.mkfifo(fifo_AB)
            os.mkfifo(fifo_BA)

            fd_AB = os.open(str(fifo_AB), os.O_RDWR)
            fd_BA = os.open(str(fifo_BA), os.O_RDWR)

            # 编译（编译缓存使后续 case 仅复制缓存，~1ms）
            user_client = (
                create_sandbox_client(
                    languages=languages_config,
                    client_cls=SandboxClient,
                )
                if languages_config
                else None
            )
            interactor_client = create_sandbox_client(
                languages=interactor_languages,
                client_cls=SandboxClient,
            )
            user_program = None
            interactor_program = None

            try:
                if user_client and source:
                    user_program = user_client.prepare_source(
                        language=language_key,
                        source=source,
                        workspace=str(work_dir),
                        isolation=isolation,
                        cgroup=cgroup,
                    )
                    ct, cm = compile_metrics_from_process(user_program.compile)
                    # 多测例时编译缓存命中耗时近 0；保留首次非零峰值
                    if ct > compile_time_ms:
                        compile_time_ms = ct
                    if cm > compile_memory_kb:
                        compile_memory_kb = cm
                    if not user_program.compiled:
                        all_cases.append(
                            {
                                "case_no": tc["case_no"],
                                "result": "CE",
                                "time_ms": 0,
                                "memory_kb": 0,
                                "points": 0.0,
                                "stdout_preview": "",
                                "stderr_preview": user_program.compile.message,
                            }
                        )
                        all_ac = False
                        continue

                interactor_program = interactor_client.prepare_source(
                    language=interactor_key,
                    source=interactor_cfg["source"],
                    workspace=str(work_dir),
                    isolation=isolation,
                    cgroup=cgroup,
                )
                if not interactor_program.compiled:
                    all_cases.append(
                        {
                            "case_no": tc["case_no"],
                            "result": "IE",
                            "time_ms": 0,
                            "memory_kb": 0,
                            "points": 0.0,

                            "stdout_preview": "",
                            "stderr_preview": interactor_program.compile.message,
                        }
                    )
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
                            isolation=isolation,
                            cgroup=cgroup,
                            capture_output=False,
                            allow_file_io=True,
                        )
                    except Exception as exc:
                        logger.error("交互判题用户程序异常: %s", exc)
                        return None

                def _try_run_interactor():
                    interactor_limits = JudgeLimits(
                        cpu_time_ms=interactor_cfg.get("time_limit_ms")
                        or problem["time_limit_ms"] * 2,
                        real_time_ms=(
                            interactor_cfg.get("time_limit_ms")
                            or problem["time_limit_ms"] * 2
                        )
                        * 2,
                        memory_bytes=(
                            interactor_cfg.get("memory_limit_kb")
                            or problem["memory_limit_kb"]
                        )
                        * 1024,
                        processes=256,
                    )
                    try:
                        return interactor_program.run_with_paths(
                            stdin_path=str(fifo_AB),
                            stdout_path=str(fifo_BA),
                            stderr_path=str(interactor_stderr_path),
                            limits=interactor_limits,
                            isolation=isolation,
                            cgroup=cgroup,
                            capture_output=False,
                            variables={"input_file": str(input_file)},
                            allow_file_io=True,
                            exit_codes_ok=[0, 1],
                        )
                    except Exception as exc:
                        logger.error("交互判题交互器异常: %s", exc)
                        return None

                timeout_seconds = max(
                    (problem["time_limit_ms"] * 5) / 1000.0, 10
                )
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
                futures = {
                    pool.submit(_try_run_user): "user",
                    pool.submit(_try_run_interactor): "interactor",
                }
                try:
                    done, pending = concurrent.futures.wait(
                        futures,
                        timeout=timeout_seconds,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for future in done:
                        holder[futures[future]] = future.result()

                    should_release_fifos = False
                    user_first = holder.get("user")
                    if user_first is not None and user_first.status != Status.AC:
                        should_release_fifos = True
                    if "interactor" in {futures[future] for future in done}:
                        should_release_fifos = True

                    if should_release_fifos:
                        if fd_AB >= 0:
                            os.close(fd_AB)
                            fd_AB = -1
                        if fd_BA >= 0:
                            os.close(fd_BA)
                            fd_BA = -1

                    if pending:
                        followup_timeout = 1.0 if should_release_fifos else timeout_seconds
                        more_done, pending = concurrent.futures.wait(
                            pending,
                            timeout=followup_timeout,
                        )
                        for future in more_done:
                            holder[futures[future]] = future.result()

                    for future in pending:
                        future.cancel()
                        logger.warning(
                            "交互判题%s超时: case=%d, timeout=%.1fs",
                            "用户程序" if futures[future] == "user" else "交互器",
                            tc["case_no"],
                            timeout_seconds,
                        )
                    if pending:
                        if fd_AB >= 0:
                            os.close(fd_AB)
                            fd_AB = -1
                        if fd_BA >= 0:
                            os.close(fd_BA)
                            fd_BA = -1
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)

                user_result = holder.get("user")
                interactor_result = holder.get("interactor")

                interactor_stderr_text = ""
                if interactor_stderr_path.exists():
                    interactor_stderr_text = interactor_stderr_path.read_text(
                        encoding="utf-8", errors="replace"
                    )[:4096]

                # 判定优先级：用户 runtime 错误 > 交互器 runtime 错误 > WA > AC
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

                time_ms = (
                    reported_run_time_ms(user_result.run) if user_result else 0
                )
                mem_kb = user_result.run.memory_bytes // 1024 if user_result else 0

                all_cases.append(
                    {
                        "case_no": tc["case_no"],
                        "result": status_str,
                        "time_ms": time_ms,
                        "memory_kb": mem_kb,
                        "points": points,

                        "stdout_preview": (
                            user_result.stdout[:2048]
                            if user_result and user_result.stdout
                            else ""
                        ),
                        "stderr_preview": interactor_stderr_text,
                    }
                )

            finally:
                if fd_AB >= 0:
                    os.close(fd_AB)
                if fd_BA >= 0:
                    os.close(fd_BA)
                if interactor_program is not None:
                    interactor_program.close()
                if user_program is not None:
                    user_program.close()
                if user_client:
                    user_client.close()
                interactor_client.close()
                shutil.rmtree(work_dir, ignore_errors=True)

        non_ac = [
            c["result"]
            for c in all_cases
            if c["result"] not in ("AC", "SKIPPED")
        ]
        overall_result = "AC" if all_ac else (non_ac[0] if non_ac else "WA")

        run_time_ms, run_memory_kb = run_metrics_from_cases(all_cases)
        return {
            "submission_id": submission_id,
            "status": "COMPLETED",
            "result": overall_result,
            "score": total_score,
            "time_ms": run_time_ms,
            "memory_kb": run_memory_kb,
            "compile_time_ms": compile_time_ms,
            "compile_memory_kb": compile_memory_kb,
            "compile_output": None,
            "compile_error": False,
            "cases": all_cases,
            "error": None,
        }
