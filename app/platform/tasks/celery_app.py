import logging

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config.settings import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "hei-fastapi",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend or settings.redis.url,
    include=["app.worker.tasks"],
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.worker_enable_remote_control = settings.celery.worker_remote_control_enabled
celery_app.conf.worker_cancel_long_running_tasks_on_connection_loss = (
    settings.celery.worker_cancel_long_running_tasks_on_connection_loss
)
celery_app.conf.worker_prefetch_multiplier = settings.celery.worker_prefetch_multiplier
celery_app.conf.redbeat_redis_url = settings.redis.url
celery_app.conf.redbeat_lock_key = "redbeat:lock"

from app.platform.tasks.redbeat_scheduler import sync_to_redbeat  # noqa: E402

sync_to_redbeat(celery_app)


@worker_process_init.connect
def _worker_process_init(**_: object) -> None:
    # Must share WorkerAsyncRunner's loop: asyncio.run() would bind Redis
    # connections to a temporary loop that is closed before tasks run.
    try:
        from app.platform.tasks.async_runner import worker_async_runner

        worker_async_runner.run(_startup_worker_infra())
    except Exception:
        logger.exception("Failed to initialize worker infrastructure")
        raise


@worker_process_shutdown.connect
def _worker_process_shutdown(**_: object) -> None:
    try:
        from app.platform.tasks.async_runner import worker_async_runner

        worker_async_runner.run(_shutdown_worker_infra())
        worker_async_runner.close()
    except Exception:
        logger.warning("Failed to shutdown worker infrastructure", exc_info=True)


async def _startup_worker_infra() -> None:
    """Judge Celery worker: init Redis; config/storage from env (STORAGE__*)."""
    from app.platform.cache.redis import init_redis

    await init_redis()
    logger.info("worker infra ready: redis; storage from STORAGE__* env")


async def _shutdown_worker_infra() -> None:
    from app.platform.cache.redis import close_redis

    await close_redis()
