import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MQMessage:
    body: bytes
    exchange: str
    routing_key: str
    delivery_tag: int
    properties: Any

    @classmethod
    def from_pika(
        cls,
        method: Any,
        properties: Any,
        body: bytes,
    ) -> "MQMessage":
        return cls(
            body=body,
            exchange=method.exchange,
            routing_key=method.routing_key,
            delivery_tag=method.delivery_tag,
            properties=properties,
        )

    @property
    def headers(self) -> dict[str, Any]:
        return dict(self.properties.headers or {})

    @property
    def content_type(self) -> str | None:
        return self.properties.content_type

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding)

    def json(self) -> Any:
        return json.loads(self.text())
