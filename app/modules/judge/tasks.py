"""Judge Celery tasks — 接收判题请求，在沙箱中执行，通过返回值传递结果。"""

import logging

from app.platform.tasks.celery_app import celery_app
from app.platform.tasks.base import BaseTask

from app.modules.judge.orchestrator import judge as _judge

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=BaseTask, name="judge.execute")
def execute_judge(self, payload: dict) -> dict:
    """同步判题，结果通过 Celery 返回值传递（无 pika 发布到 MQ）。"""
    submission_id = payload.get("submission_id", "?")
    logger.info("Judge task received: %s", submission_id)
    result = _judge(payload)
    logger.info(
        "Judge task completed: %s result=%s",
        submission_id,
        result.get("result"),
    )
    return result
