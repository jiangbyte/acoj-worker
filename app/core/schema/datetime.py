from datetime import UTC, datetime
from typing import Any, get_args, get_origin


def ensure_utc_datetime(value: datetime) -> datetime:
    """将任意带时区的时间统一转换为 UTC，禁止无时区时间直接入模。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must include timezone information")
    return value.astimezone(UTC)


def format_utc_iso8601(value: datetime) -> str:
    """将时间序列化为标准 ISO 8601 UTC 字符串，并统一输出 `Z` 后缀。"""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def serialize_datetime_value(value):
    """递归序列化响应载荷中的 datetime，覆盖 ApiResponse.data 的嵌套结构。"""
    if isinstance(value, datetime):
        return format_utc_iso8601(value)
    if isinstance(value, dict):
        return {key: serialize_datetime_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_datetime_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(serialize_datetime_value(item) for item in value)
    if isinstance(value, set):
        return [serialize_datetime_value(item) for item in value]
    return value


def normalize_orm_datetimes(item: object) -> None:
    """将 ORM 对象中数据库驱动返回的 naive datetime 视为 UTC。"""
    values = getattr(item, "__dict__", {})
    for field_name, value in values.items():
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            setattr(item, field_name, value.replace(tzinfo=UTC))


def is_datetime_annotation(annotation: Any) -> bool:
    """判断字段注解是否为 datetime 或包含 datetime 的联合类型。"""
    if annotation is datetime:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    return datetime in get_args(annotation)
