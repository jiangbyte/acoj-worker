"""Judge Celery 侧配置：在任务模块加载时应用到上游 celery_app，不改 platform 文件。"""

from __future__ import annotations

import logging

from kombu import Queue

from app.modules.judge.config import get_judge_settings
from app.platform.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_configured = False


def configure_celery_app() -> None:
    """将 judge 队列与超时等应用到共享 celery_app（幂等）。"""
    global _configured
    if _configured:
        return

    cfg = get_judge_settings()
    queue = cfg.task_default_queue
    celery_app.conf.task_default_queue = queue
    celery_app.conf.task_default_routing_key = cfg.task_default_routing_key
    celery_app.conf.task_queues = (Queue(queue, routing_key=f"{queue}.#"),)
    celery_app.conf.task_soft_time_limit = cfg.task_soft_time_limit
    celery_app.conf.task_time_limit = cfg.task_time_limit
    celery_app.conf.task_acks_late = cfg.task_acks_late
    celery_app.conf.task_reject_on_worker_lost = cfg.task_reject_on_worker_lost
    # Fairness under contest load: do not prefetch a backlog of long TLE jobs.
    celery_app.conf.worker_prefetch_multiplier = cfg.worker_prefetch_multiplier
    celery_app.conf.result_backend_transport_options = {"polling_interval": 0.1}
    # Link callbacks from API still need the return value in the message body.
    celery_app.conf.task_ignore_result = False

    _configured = True
    logger.info(
        "judge celery configured: queue=%s prefetch=%s soft_limit=%s hard_limit=%s",
        queue,
        cfg.worker_prefetch_multiplier,
        cfg.task_soft_time_limit,
        cfg.task_time_limit,
    )


configure_celery_app()
