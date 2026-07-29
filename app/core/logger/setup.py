import logging
from pathlib import Path

from app.core.config.settings import settings
from app.platform.observability.logging import build_log_formatter


def setup_logging() -> None:
    root = logging.getLogger()

    # Always add stdout handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stdout = logging.StreamHandler()
        stdout.setFormatter(build_log_formatter())
        root.addHandler(stdout)

    # Add file handler if log_dir is configured
    log_dir = settings.observability.log_dir
    if log_dir:
        # Resolve to absolute path if relative
        if not Path(log_dir).is_absolute():
            log_dir = str(Path.cwd() / log_dir)
        try:
            from app.core.logger.file_handler import DailyFileHandler

            fh = DailyFileHandler(log_dir)
            fh.setFormatter(build_log_formatter())
            root.addHandler(fh)
        except Exception:
            logging.getLogger(__name__).exception("Failed to initialize file logging")

    root.setLevel(getattr(logging, settings.observability.log_level.upper(), logging.INFO))
