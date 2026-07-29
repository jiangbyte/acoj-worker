from collections.abc import Iterable
from typing import Annotated, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.core.schema.datetime import (
    ensure_utc_datetime,
    is_datetime_annotation,
    normalize_orm_datetimes,
    serialize_datetime_value,
)

SchemaT = TypeVar("SchemaT", bound="ApiSchema")
Id = Annotated[str, Field(min_length=1, max_length=64)]


class ApiSchema(BaseModel):
    """全局基础 DTO，统一承担时间标准化与 JSON 序列化策略。"""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_datetime_fields(self, value):
        """在响应序列化阶段将所有 datetime 字段统一转成 ISO 8601 UTC 字符串。"""
        return serialize_datetime_value(value)

    @model_validator(mode="after")
    def normalize_datetimes(self):
        """在模型创建后规范化 datetime 字段，确保内部始终持有 UTC 时间对象。"""
        for field_name, field_info in self.__class__.model_fields.items():
            if not is_datetime_annotation(field_info.annotation):
                continue
            value = getattr(self, field_name, None)
            if value is not None:
                setattr(self, field_name, ensure_utc_datetime(value))
        return self


class IdQuery(ApiSchema):
    id: Id


class IdsRequest(ApiSchema):
    ids: list[Id] = Field(min_length=1)


def to_schema(schema_cls: type[SchemaT], item: object) -> SchemaT:
    """Convert ORM/entity objects to API schemas through Pydantic attributes mode."""
    normalize_orm_datetimes(item)
    return schema_cls.model_validate(item)


def to_schema_list(schema_cls: type[SchemaT], items: Iterable[object]) -> list[SchemaT]:
    """Convert a list of ORM/entity objects to API schemas."""
    return [to_schema(schema_cls, item) for item in items]
