import json
import logging
from datetime import datetime, UTC

from app.core.config.settings import settings
from app.core.schema.datetime import format_utc_iso8601
from app.core.logger.formatter import RequestFormatter
from app.platform.observability.context import get_log_context


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": format_utc_iso8601(datetime.now(UTC)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(get_log_context())
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def build_log_formatter() -> logging.Formatter:
    """按当前配置构建日志格式化器，普通文本日志也需要补齐请求上下文字段。"""
    if settings.observability.enabled and settings.observability.log_json:
        return JsonLogFormatter()
    return RequestFormatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
