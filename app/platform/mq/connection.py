from typing import Any

from app.core.config.settings import settings


def mq_url() -> str:
    return settings.mq.url or settings.celery.broker_url


def import_pika() -> Any:
    try:
        import pika
    except ModuleNotFoundError as exc:
        raise RuntimeError("MQ support requires the 'pika' package to be installed") from exc
    return pika


def create_blocking_connection(url: str | None = None) -> Any:
    pika = import_pika()
    return pika.BlockingConnection(pika.URLParameters(url or mq_url()))
