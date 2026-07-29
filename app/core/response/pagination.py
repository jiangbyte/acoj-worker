from math import ceil
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import Field

from app.core.schema.base import ApiSchema

T = TypeVar("T")

Current = Annotated[int, Query(ge=1, description="Current page")]
Size = Annotated[int, Query(ge=1, le=100, description="Page size")]


class PageQuery(ApiSchema):
    current: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.current - 1) * self.size


class PageData(ApiSchema, Generic[T]):
    """标准分页响应体，统一返回页码、总量和当前页数据。"""

    size: int
    current: int
    total: int
    pages: int
    records: list[T]


def build_page(query: PageQuery, total: int, items: list[T]) -> PageData[T]:
    """构造统一分页模型，避免各路由重复计算总页数和手工拼装字典。"""
    return PageData(
        size=query.size,
        current=query.current,
        total=total,
        pages=ceil(total / query.size) if total else 0,
        records=items,
    )
