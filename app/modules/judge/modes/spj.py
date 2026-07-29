"""SPECIAL_JUDGE 判题模式：编译用户程序 + 编译 checker → 逐用例运行。

优化：checker 编译一次，per-case 复用 prepared_checker 跳过重编译。
checker 用 testlib_checker_language 编译以确保正确的 run_argv。
"""

import logging
import time as time_module

from acoj_sandbox import (
    DataRef,
    SandboxClient,
    Status,
    LanguagesConfig,
    testlib_checker_language,
)

from app.modules.judge.case_builder import build_judge_limits
from app.modules.judge.data_loader import resolve_input_ref, resolve_output_ref
from app.modules.judge.language_config import build_languages_config
from app.modules.judge.modes.base import BaseJudgeMode
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


class SpecialJudgeMode(BaseJudgeMode):
    """SPJ 判题模式。"""

    def judge(self, payload: dict) -> dict:
        submission_id = payload["submission_id"]
        problem = payload["problem"]
        language_cfg = payload["language"]
        source = payload["source"]
        spj_cfg = payload.get("spj", {})
        test_cases_data = payload["test_cases"]

        if not spj_cfg.get("source"):
            return error_verdict(submission_id, "缺少 SPJ checker 源码")

        languages_config = build_languages_config(language_cfg)
        language_key = language_cfg["key"]

        # checker 用 testlib_checker_language 编译（确保 run_argv 含 input/output/answer 参数）
        checker_lang_spec = testlib_checker_language()
        checker_languages = LanguagesConfig([checker_lang_spec])
        checker_key = checker_lang_spec.id

        isolation = build_isolation_config()
        cgroup = build_cgroup_config()

        client = create_sandbox_client(
            languages=languages_config,
            client_cls=SandboxClient,
        )
        checker_client = create_sandbox_client(
            languages=checker_languages,
            client_cls=SandboxClient,
        )
        program = None
        checker_program = None
        compile_time_ms = 0
        compile_memory_kb = 0
        try:
            program = client.prepare_source(
                language=language_key,
                source=source,
                isolation=isolation,
                cgroup=cgroup,
            )
            compile_time_ms, compile_memory_kb = compile_metrics_from_process(
                program.compile
            )
            if not program.compiled:
                return error_verdict(
                    submission_id,
                    f"用户程序编译失败: {program.compile.message}",
                )

            # 编译 checker（一次，per-case 复用）
            checker_program = checker_client.prepare_source(
                language=checker_key,
                source=spj_cfg["source"],
                isolation=isolation,
                cgroup=cgroup,
            )
            if not checker_program.compiled:
                return error_verdict(
                    submission_id,
                    f"SPJ checker 编译失败: {checker_program.compile.message}",
                )

            all_cases: list[dict] = []
            all_ac = True
            total_score = 0.0
            per_case_points = problem["points"] / max(len(test_cases_data), 1)

            for tc in test_cases_data:
                input_ref = resolve_input_ref(tc)
                expected_ref = resolve_output_ref(tc)
                case_limits = build_judge_limits(tc, problem)

                user_result = program.run(
                    input_data=input_ref.data or "",
                    input=input_ref,
                    limits=case_limits,
                    isolation=isolation,
                    cgroup=cgroup,
                )
                user_ac = user_result.status == Status.AC

                # 复用已编译的 checker
                spj_result = client.run_testlib_checker(
                    checker_source=spj_cfg["source"],
                    input=input_ref,
                    actual_output=DataRef.from_path(user_result.stdout_path),
                    expected_output=expected_ref or DataRef.from_data(""),
                    prepared_checker=checker_program,
                    isolation=isolation,
                    cgroup=cgroup,
                )

                case_ac = user_ac and spj_result.accepted
                points = per_case_points if case_ac else 0.0
                if case_ac:
                    total_score += points
                else:
                    all_ac = False

                all_cases.append(
                    {
                        "case_no": tc["case_no"],
                        "result": "AC" if case_ac else "WA",
                        "time_ms": reported_run_time_ms(user_result.run),
                        "memory_kb": user_result.run.memory_bytes // 1024,
                        "points": points,
                        "stdout_preview": DataRef.from_path(
                            user_result.stdout_path
                        ).preview_text,
                        "stderr_preview": DataRef.from_path(
                            user_result.stderr_path
                        ).preview_text,
                    }
                )
        finally:
            if checker_program is not None:
                checker_program.close()
            if program is not None:
                program.close()
            client.close()
            checker_client.close()

        run_time_ms, run_memory_kb = run_metrics_from_cases(all_cases)
        return {
            "submission_id": submission_id,
            "status": "COMPLETED",
            "result": "AC" if all_ac else "WA",
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
