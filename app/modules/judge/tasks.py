"""Judge Celery tasks — 经 Celery/RabbitMQ 收任务，结果写入 Redis backend，可跨进程 AsyncResult 查询。"""

import logging

from pydantic import ValidationError

import app.modules.judge.celery_setup  # noqa: F401  # apply judge queue/timeouts
from app.modules.judge.orchestrator import judge as _judge
from app.modules.judge.schemas import JudgePayload, JudgeResultOut
from app.platform.tasks.base import BaseTask
from app.platform.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _failed_result(submission_id: str, error: str) -> dict:
    return JudgeResultOut(
        submission_id=submission_id or "?",
        status="FAILED",
        error=error,
    ).model_dump()


@celery_app.task(bind=True, base=BaseTask, name="judge.execute")
def execute_judge(self, payload: dict) -> dict:
    """同步判题。入站 RabbitMQ；出站 Redis result backend（可跨进程按 task_id 查询）。"""
    submission_id = "?"
    if isinstance(payload, dict):
        submission_id = str(payload.get("submission_id") or "?")

    try:
        JudgePayload.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Judge payload invalid: %s", submission_id)
        return _failed_result(submission_id, f"invalid payload: {exc}")

    logger.info("Judge task received: %s", submission_id)
    result = _judge(payload)
    # 规范化为 JudgeResultOut 形状，保证 Celery 返回值协议稳定
    result = JudgeResultOut.model_validate(result).model_dump()
    logger.info(
        "Judge task completed: %s result=%s",
        submission_id,
        result.get("result"),
    )
    return result
