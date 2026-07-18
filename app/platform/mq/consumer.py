import asyncio
import inspect
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from app.core.config.settings import settings
from app.platform.mq.connection import create_blocking_connection
from app.platform.mq.message import MQMessage
from app.platform.tasks.async_runner import worker_async_runner

logger = logging.getLogger(__name__)

ChannelSetup = Callable[[Any], str]
MessageHandler = Callable[[MQMessage], Any]


class MQConsumerWorker:
    """Reusable blocking RabbitMQ consumer worker for modules.

    The module owns queue/exchange declaration through ``setup_channel``. The
    callback receives the raw pika channel and must return the queue name to
    consume from, so modules can use any RabbitMQ topology they need.
    """

    def __init__(
        self,
        *,
        name: str,
        setup_channel: ChannelSetup,
        handler: MessageHandler,
        auto_ack: bool = False,
        prefetch_count: int = 1,
        requeue_on_error: bool = False,
        reconnect_interval_seconds: float | None = None,
    ) -> None:
        self.name = name
        self.setup_channel = setup_channel
        self.handler = handler
        self.auto_ack = auto_ack
        self.prefetch_count = prefetch_count
        self.requeue_on_error = requeue_on_error
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"mq-consumer-{name}", daemon=True)

    def start(self) -> None:
        if not settings.mq.enabled:
            return
        if self._thread.is_alive():
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    async def stop_async(self) -> None:
        self.stop()
        await asyncio.to_thread(self.join)

    def join(self) -> None:
        self._thread.join(timeout=settings.celery.shutdown_timeout_seconds)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._consume()
            except Exception:
                if self._stop_event.is_set():
                    return
                logger.exception("MQ consumer crashed; reconnecting", extra={"consumer": self.name})
                reconnect_interval = (
                    self.reconnect_interval_seconds or settings.mq.reconnect_interval_seconds
                )
                time.sleep(reconnect_interval)

    def _consume(self) -> None:
        connection = create_blocking_connection()
        try:
            channel = connection.channel()
            queue = self.setup_channel(channel)
            if self.prefetch_count > 0:
                channel.basic_qos(prefetch_count=self.prefetch_count)
            channel.basic_consume(
                queue=queue,
                on_message_callback=self._callback(),
                auto_ack=self.auto_ack,
                consumer_tag=self.name,
            )
            logger.info("MQ consumer started", extra={"consumer": self.name, "queue": queue})
            while not self._stop_event.is_set():
                connection.process_data_events(time_limit=1)
        finally:
            try:
                connection.close()
            except Exception:
                logger.debug("MQ connection close failed", exc_info=True)

    def _callback(self) -> Callable:
        def callback(channel, method, properties, body: bytes) -> None:
            message = MQMessage.from_pika(method, properties, body)
            try:
                result = self.handler(message)
                if inspect.isawaitable(result):
                    worker_async_runner.run(result)
                if not self.auto_ack:
                    channel.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                logger.exception(
                    "MQ message handler failed",
                    extra={
                        "consumer": self.name,
                        "exchange": message.exchange,
                        "routing_key": message.routing_key,
                    },
                )
                if not self.auto_ack:
                    channel.basic_nack(
                        delivery_tag=method.delivery_tag,
                        requeue=self.requeue_on_error,
                    )

        return callback


class MQConsumerGroup:
    def __init__(self, workers: list[MQConsumerWorker] | None = None) -> None:
        self.workers = workers or []

    def add(self, worker: MQConsumerWorker) -> None:
        self.workers.append(worker)

    def start(self) -> None:
        for worker in self.workers:
            worker.start()

    async def stop(self) -> None:
        for worker in self.workers:
            worker.stop()
        for worker in self.workers:
            await asyncio.to_thread(worker.join)
