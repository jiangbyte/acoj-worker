from __future__ import annotations

import json
from types import UnionType
from typing import Any, Union, get_args, get_origin


def coerce_config_value(value: Any, annotation: Any) -> Any:
    """Coerce DB string config values into the declared settings field type."""
    if value is None:
        return None

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (UnionType, Union):
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return coerce_config_value(value, non_none_args[0])

    if annotation is str:
        return str(value)
    if annotation is bool:
        return _coerce_bool(value)
    if annotation is int:
        return _coerce_int(value)
    if annotation is float:
        return _coerce_float(value)
    if origin is list:
        return _coerce_json(value, list)
    if origin is dict or annotation is dict:
        return _coerce_json(value, dict)

    try:
        return annotation(value)
    except Exception:
        return value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_json(value: Any, expected_type: type) -> Any:
    if isinstance(value, expected_type):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, expected_type) else None
