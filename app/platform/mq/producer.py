import asyncio
import json
from collections.abc import Mapping
from typing import Any

from app.core.config.settings import settings
from app.platform.mq.connection import create_blocking_connection, import_pika


class EventProducer:
    async def publish(
        self,
        topic: str,
        payload: Any,
        *,
        exchange: str | None = None,
        routing_key: str | None = None,
        exchange_type: str | None = None,
        declare_exchange: bool = True,
        durable_exchange: bool = True,
        mandatory: bool = False,
        headers: Mapping[str, Any] | None = None,
        content_type: str | None = None,
        delivery_mode: int | None = 2,
        properties: Any | None = None,
        property_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self.publish_sync,
            topic,
            payload,
            exchange=exchange,
            routing_key=routing_key,
            exchange_type=exchange_type,
            declare_exchange=declare_exchange,
            durable_exchange=durable_exchange,
            mandatory=mandatory,
            headers=headers,
            content_type=content_type,
            delivery_mode=delivery_mode,
            properties=properties,
            property_kwargs=property_kwargs,
        )

    def publish_sync(
        self,
        topic: str,
        payload: Any,
        *,
        exchange: str | None = None,
        routing_key: str | None = None,
        exchange_type: str | None = None,
        declare_exchange: bool = True,
        durable_exchange: bool = True,
        mandatory: bool = False,
        headers: Mapping[str, Any] | None = None,
        content_type: str | None = None,
        delivery_mode: int | None = 2,
        properties: Any | None = None,
        property_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        body, resolved_content_type = _encode_payload(payload, content_type)
        pika = import_pika()
        resolved_exchange = settings.mq.publish_exchange if exchange is None else exchange
        resolved_exchange_type = exchange_type or settings.mq.publish_exchange_type
        resolved_routing_key = topic if routing_key is None else routing_key
        connection = create_blocking_connection()
        try:
            channel = connection.channel()
            if declare_exchange and resolved_exchange:
                channel.exchange_declare(
                    exchange=resolved_exchange,
                    exchange_type=resolved_exchange_type,
                    durable=durable_exchange,
                )
            channel.basic_publish(
                exchange=resolved_exchange,
                routing_key=resolved_routing_key,
                body=body,
                mandatory=mandatory,
                properties=properties
                or pika.BasicProperties(
                    content_type=resolved_content_type,
                    delivery_mode=delivery_mode,
                    headers=dict(headers or {}),
                    **dict(property_kwargs or {}),
                ),
            )
        finally:
            connection.close()


def _encode_payload(
    payload: Any,
    content_type: str | None,
) -> tuple[bytes, str | None]:
    if isinstance(payload, bytes):
        return payload, content_type
    if isinstance(payload, str):
        return payload.encode("utf-8"), content_type or "text/plain"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return body, content_type or "application/json"


event_producer = EventProducer()
