import asyncio
import logging

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config.settings import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "hei-fastapi",
    broker=settings.celery.broker_url,
    backend=settings.redis.url,
    include=["app.worker.tasks"],
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.worker_enable_remote_control = settings.celery.worker_remote_control_enabled
celery_app.conf.worker_cancel_long_running_tasks_on_connection_loss = (
    settings.celery.worker_cancel_long_running_tasks_on_connection_loss
)
celery_app.conf.redbeat_redis_url = settings.redis.url
celery_app.conf.redbeat_lock_key = "redbeat:lock"

from app.platform.tasks.redbeat_scheduler import sync_to_redbeat  # noqa: E402

sync_to_redbeat(celery_app)


@worker_process_init.connect
def _worker_process_init(**_: object) -> None:
    try:
        asyncio.run(_startup_worker_infra())
    except Exception:
        logger.exception("Failed to initialize worker infrastructure")
        raise


@worker_process_shutdown.connect
def _worker_process_shutdown(**_: object) -> None:
    try:
        asyncio.run(_shutdown_worker_infra())
    except Exception:
        logger.warning("Failed to shutdown worker infrastructure", exc_info=True)


async def _startup_worker_infra() -> None:
    from app.platform.cache.redis import init_redis
    from app.platform.config.apply import apply_all_config
    from app.platform.config.reader import config_reader
    from app.platform.config.sync import start_config_sync_listener_thread
    from app.platform.db.session import init_engine

    init_engine()
    await init_redis()
    await config_reader.load_all()
    apply_all_config()
    start_config_sync_listener_thread()


async def _shutdown_worker_infra() -> None:
    from app.platform.cache.redis import close_redis
    from app.platform.config.sync import stop_config_sync_listener_thread
    from app.platform.db.session import close_engine

    stop_config_sync_listener_thread()
    await close_redis()
    await close_engine()
