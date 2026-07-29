import time
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

from app.core.config.settings import settings

registry = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
    registry=registry,
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    registry=registry,
)
http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Current in-flight HTTP requests",
    ["method", "path"],
    registry=registry,
)
app_exceptions_total = Counter(
    "app_exceptions_total",
    "Total application exceptions",
    ["exception_type"],
    registry=registry,
)
validation_errors_total = Counter(
    "validation_errors_total",
    "Total validation errors",
    registry=registry,
)
http_client_requests_total = Counter(
    "http_client_requests_total",
    "Total outbound HTTP client requests",
    ["method", "host", "status_code"],
    registry=registry,
)
http_client_request_duration_seconds = Histogram(
    "http_client_request_duration_seconds",
    "Outbound HTTP client request duration",
    ["method", "host"],
    registry=registry,
)
celery_task_total = Counter(
    "celery_task_total",
    "Total Celery task executions",
    ["task_name", "status"],
    registry=registry,
)
celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration",
    ["task_name"],
    registry=registry,
)
auth_login_total = Counter(
    "auth_login_total",
    "Total login attempts",
    ["account_type", "result", "reason"],
    registry=registry,
)
auth_login_lock_total = Counter(
    "auth_login_lock_total",
    "Total login lock events",
    ["account_type", "scope"],
    registry=registry,
)
operation_audit_total = Counter(
    "operation_audit_total",
    "Total operation audit events",
    ["module", "action", "result"],
    registry=registry,
)
file_upload_rejected_total = Counter(
    "file_upload_rejected_total",
    "Total rejected file uploads",
    ["reason"],
    registry=registry,
)
def metrics_enabled() -> bool:
    return settings.observability.enabled and settings.observability.metrics_enabled


def metrics_response() -> Response:
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@contextmanager
def track_http_request(method: str, path: str):
    if not metrics_enabled():
        yield lambda status_code: None
        return
    in_progress = http_requests_in_progress.labels(method=method, path=path)
    in_progress.inc()
    start = time.perf_counter()

    def finalize(status_code: int) -> None:
        duration = time.perf_counter() - start
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)
        http_requests_total.labels(method=method, path=path, status_code=str(status_code)).inc()
        in_progress.dec()

    try:
        yield finalize
    except Exception:
        in_progress.dec()
        raise


def record_app_exception(exception_type: str) -> None:
    if metrics_enabled():
        app_exceptions_total.labels(exception_type=exception_type).inc()


def record_validation_error() -> None:
    if metrics_enabled():
        validation_errors_total.inc()


def record_login_attempt(account_type: str, result: str, reason: str = "none") -> None:
    if metrics_enabled():
        auth_login_total.labels(account_type=account_type, result=result, reason=reason).inc()


def record_login_lock(account_type: str, scope: str) -> None:
    if metrics_enabled():
        auth_login_lock_total.labels(account_type=account_type, scope=scope).inc()


def record_operation_audit(module: str, action: str, success: bool) -> None:
    if metrics_enabled():
        operation_audit_total.labels(
            module=module,
            action=action,
            result="success" if success else "failure",
        ).inc()


def record_file_upload_rejected(reason: str) -> None:
    if metrics_enabled():
        file_upload_rejected_total.labels(reason=reason).inc()


@contextmanager
def track_http_client_request(method: str, host: str):
    if not metrics_enabled():
        yield lambda status_code: None
        return
    start = time.perf_counter()

    def finalize(status_code: int) -> None:
        duration = time.perf_counter() - start
        http_client_request_duration_seconds.labels(method=method, host=host).observe(duration)
        http_client_requests_total.labels(
            method=method,
            host=host,
            status_code=str(status_code),
        ).inc()

    yield finalize


@contextmanager
def track_celery_task(task_name: str):
    if not metrics_enabled():
        yield lambda status: None
        return
    start = time.perf_counter()

    def finalize(status: str) -> None:
        duration = time.perf_counter() - start
        celery_task_total.labels(task_name=task_name, status=status).inc()
        celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

    yield finalize
