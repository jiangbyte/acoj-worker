"""Judge worker module spec — 注册 MQ 消费者和生命周期钩子。"""

from app.platform.module import ModuleSpec
from app.platform.mq.consumer import MQConsumerWorker
from app.modules.judge.handler import handle_judge_request


def _setup_channel(channel) -> str:
    exchange = "oj.judge"
    queue = "oj.judge.request"
    channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
    channel.queue_declare(queue=queue, durable=True)
    channel.queue_bind(queue=queue, exchange=exchange, routing_key="request")
    return queue


judge_consumer = MQConsumerWorker(
    name="judge-request",
    setup_channel=_setup_channel,
    handler=handle_judge_request,
    auto_ack=False,
    prefetch_count=1,
)


def _start():
    judge_consumer.start()


def _stop():
    return judge_consumer.stop_async()


module = ModuleSpec(
    name="judge",
    startup_hooks=(f"{__name__}:_start",),
    shutdown_hooks=(f"{__name__}:_stop",),
)
