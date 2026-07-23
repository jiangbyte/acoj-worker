from celery import Celery
from kombu import Queue

from app.core.config.settings import settings

celery_app = Celery(
    "acoj-worker",
    broker=settings.celery.broker_url,
    backend=settings.redis.url,
    include=["app.modules.judge.tasks"],
)
celery_app.conf.task_default_queue = "judge"
celery_app.conf.task_default_routing_key = "judge.default"
celery_app.conf.task_queues = (
    Queue("judge", routing_key="judge.#"),
)
celery_app.conf.worker_enable_remote_control = settings.celery.worker_remote_control_enabled
celery_app.conf.worker_cancel_long_running_tasks_on_connection_loss = (
    settings.celery.worker_cancel_long_running_tasks_on_connection_loss
)
celery_app.conf.task_soft_time_limit = 300
celery_app.conf.task_time_limit = 600
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = settings.celery.worker_prefetch_multiplier
celery_app.conf.result_backend_transport_options = {
    "polling_interval": 0.1,
}
celery_app.conf.redbeat_redis_url = settings.redis.url
celery_app.conf.redbeat_lock_key = "redbeat:lock"
celery_app.conf.redbeat_lock_timeout = 30

from app.platform.tasks.redbeat_scheduler import sync_to_redbeat  # noqa: E402
sync_to_redbeat(celery_app)
