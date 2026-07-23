"""STANDARD 判题模式：编译 + 批量运行 + 输出比对 + 计分。

支持的评分策略：
  - ACM：首错即停（stop_on_first）
  - OI：逐点累加（case-level points）
  - IOI：同 batch 全过才给分（batch_no + batch_depends）
"""

import logging
import time as time_module

from acoj_sandbox import SandboxClient, Status

from app.core.config.settings import settings
from app.modules.judge.case_builder import build_judge_cases, get_expected_text
from app.modules.judge.checker import check_output
from app.modules.judge.language_config import build_languages_config
from app.modules.judge.modes.base import BaseJudgeMode
from app.modules.judge.result_mapper import compute_overall_result, to_oj_result
from app.modules.judge.sandbox_config import (
    build_cgroup_config,
    build_isolation_config,
    create_sandbox_client,
)
from app.modules.judge.scoring import aggregate_batches, error_verdict

logger = logging.getLogger(__name__)


class StandardMode(BaseJudgeMode):
    """STANDARD 判题模式：ACM / OI / IOI。"""

    def judge(self, payload: dict) -> dict:
        submission_id = payload["submission_id"]
        problem = payload["problem"]
        language_cfg = payload["language"]
        source = payload["source"]
        test_cases_data = payload["test_cases"]
        partial = problem.get("partial", False)

        languages_config = build_languages_config(language_cfg)
        language_key = language_cfg["key"]

        cases = build_judge_cases(test_cases_data, problem)
        if not cases:
            return error_verdict(submission_id, "没有测试点数据")

        client = create_sandbox_client(
            languages=languages_config,
            client_cls=SandboxClient,
        )
        batch_result = None
        try:
            isolation = build_isolation_config()
            cgroup = build_cgroup_config()
            parallelism = max(1, settings.celery.sandbox_standard_parallelism)
            batch_result = client.run_cases(
                language=language_key,
                source=source,
                cases=cases,
                isolation=isolation,
                cgroup=cgroup,
                stop_on_first_failure=False,
                parallelism=min(parallelism, len(cases)),
            )

            has_ce = batch_result.compile.status != Status.AC
            has_batch = any(tc.get("batch_no") for tc in test_cases_data)
            stop_on_first = not partial and not has_batch

            raw_case_results: list[dict] = []
            had_failure = False

            for i, case_result in enumerate(batch_result.cases):
                if stop_on_first and had_failure:
                    raw_case_results.append(self._skipped_result(i + 1))
                    continue

                tc_meta = test_cases_data[i] if i < len(test_cases_data) else {}
                sandbox_status = case_result.status
                run_ok = sandbox_status == Status.AC

                expected_text = get_expected_text(case_result, tc_meta)
                output_match = run_ok and (
                    not expected_text
                    or check_output(case_result.actual_output.preview_text, expected_text)
                )
                oj_result = (
                    "AC"
                    if (run_ok and output_match)
                    else (to_oj_result(sandbox_status) if not run_ok else "WA")
                )

                if oj_result != "AC":
                    had_failure = True

                raw_case_results.append(
                    {
                        "case_no": i + 1,
                        "result": oj_result,
                        "time_ms": case_result.result.run.cpu_time_ms,
                        "memory_kb": case_result.result.run.memory_bytes // 1024,
                        "points": tc_meta.get("points", 0),
                        "stdout_preview": case_result.actual_output.preview_text,
                        "stderr_preview": case_result.stderr.preview_text,
                    }
                )

            if has_batch:
                case_results, score = aggregate_batches(raw_case_results, test_cases_data)
            else:
                case_results = raw_case_results
                score = 0.0 if has_ce else sum(
                    c["points"] for c in case_results if c["result"] == "AC"
                )

            if has_ce:
                overall_result = "CE"
            elif score >= problem["points"]:
                overall_result = "AC"
            else:
                overall_result = compute_overall_result(False, case_results)

            return {
                "submission_id": submission_id,
                "status": "COMPLETED",
                "result": overall_result,
                "score": score,
                "time_ms": batch_result.total_cpu_time_ms,
                "memory_kb": batch_result.peak_memory_bytes // 1024,
                "compile_output": batch_result.compile.message or batch_result.message,
                "compile_error": has_ce,
                "cases": case_results,
                "error": None,
            }
        finally:
            if batch_result is not None:
                batch_result.close()
            client.close()

    @staticmethod
    def _skipped_result(case_no: int) -> dict:
        return {
            "case_no": case_no,
            "result": "SKIPPED",
            "time_ms": 0,
            "memory_kb": 0,
            "points": 0,
            "stdout_preview": "",
            "stderr_preview": "",
        }
