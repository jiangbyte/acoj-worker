"""判题编排层：同步入口函数，根据 judge_mode 派发到对应策略类。"""

import logging
import time as time_module

from app.modules.judge.modes import MODE_REGISTRY

logger = logging.getLogger(__name__)


def judge(payload: dict) -> dict:
    """同步判题入口：派发 → 执行 → 返回 result dict。纯函数，无 I/O 副作用。"""
    judge_mode = payload.get("judge_mode", "STANDARD")
    submission_id = payload.get("submission_id", "?")
    logger.info("Judge task received: submission_id=%s", submission_id)
    t_start = time_module.monotonic()

    try:
        mode_cls = MODE_REGISTRY.get(judge_mode, MODE_REGISTRY["STANDARD"])
        result_payload = mode_cls().judge(payload)
    except Exception as exc:
        logger.exception("判题执行失败: %s", submission_id)
        result_payload = _build_failed_result(payload, exc, t_start)

    result_payload["wall_time_ms"] = int(
        (time_module.monotonic() - t_start) * 1000
    )
    return result_payload


def _build_failed_result(payload: dict, exc: Exception, t_start: float) -> dict:
    return {
        "submission_id": payload.get("submission_id", "?"),
        "status": "FAILED",
        "result": None,
        "score": 0.0,
        "time_ms": 0,
        "memory_kb": 0,
        "compile_time_ms": 0,
        "compile_memory_kb": 0,
        "compile_output": None,
        "compile_error": False,
        "cases": [],
        "error": str(exc),
        "wall_time_ms": int((time_module.monotonic() - t_start) * 1000),
    }
