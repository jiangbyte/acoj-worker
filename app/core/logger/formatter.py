import logging

from app.core.logger.context import get_request_id
from app.platform.observability.context import get_log_context


class RequestFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.request_id = get_request_id() or "-"
        context = get_log_context()
        record.trace_id = context["trace_id"] or "-"
        record.span_id = context["span_id"] or "-"
        return super().format(record)
