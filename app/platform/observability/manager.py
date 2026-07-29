from fastapi import FastAPI

from app.core.config.settings import settings
from app.platform.observability.metrics import metrics_enabled, metrics_response
from app.platform.observability.tracing import init_tracing


def setup_observability(app: FastAPI) -> None:
    if settings.observability.enabled:
        init_tracing(app=app)
    if metrics_enabled():
        app.add_api_route(settings.observability.metrics_path, metrics_response, methods=["GET"], include_in_schema=False)
