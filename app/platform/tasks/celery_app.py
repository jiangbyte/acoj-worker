from celery import Celery

from app.core.config.settings import settings

celery_app = Celery(
    "hei-fastapi",
    broker=settings.celery.broker_url,
    include=[],
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.worker_enable_remote_control = settings.celery.worker_remote_control_enabled
celery_app.conf.worker_cancel_long_running_tasks_on_connection_loss = (
    settings.celery.worker_cancel_long_running_tasks_on_connection_loss
)

from app.platform.tasks import scheduler  # noqa: E402,F401
