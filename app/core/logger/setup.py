import logging

from app.core.config.settings import settings
from app.platform.observability.logging import build_log_formatter


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(build_log_formatter())
    root.setLevel(getattr(logging, settings.observability.log_level.upper(), logging.INFO))
    root.addHandler(handler)
