"""Daily rotating file handler — writes logs to logs/YYYY/MM/DD-{pid}.log.

Supports size-based rotation and multi-process safety through PID-based
file naming (no file locking needed).
"""
import logging
import os
from datetime import datetime

from app.core.config.settings import settings


class DailyFileHandler(logging.Handler):
    def __init__(self, log_dir: str | None = None) -> None:
        super().__init__()
        self._log_dir = log_dir or settings.observability.log_dir
        self._max_bytes = settings.observability.log_file_max_mb * 1024 * 1024
        self._pid = os.getpid()
        self._formatter = None
        self._file = None
        self._current_path: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record to the current day's file."""
        path = self._daily_path()
        if path != self._current_path:
            self._close()
            self._ensure_dir(path)
            self._current_path = path
            self._file = open(path, "a", encoding="utf-8")

        if self._file and self._check_rollover():
            self._close()
            self._rotate(path)
            self._ensure_dir(path)
            self._file = open(path, "a", encoding="utf-8")

        if self._file:
            try:
                msg = self.format(record)
                self._file.write(msg + "\n")
                self._file.flush()
            except Exception:
                self.handleError(record)

    def _daily_path(self) -> str:
        """Build the daily log file path."""
        now = datetime.now()
        return os.path.join(
            self._log_dir,
            str(now.year),
            f"{now.month:02d}",
            f"{now.day:02d}-{self._pid}.log",
        )

    def _ensure_dir(self, path: str) -> None:
        dirname = os.path.dirname(path)
        if not os.path.exists(dirname):
            try:
                os.makedirs(dirname, exist_ok=True)
            except OSError:
                pass

    def _check_rollover(self) -> bool:
        """Check if current file exceeds max size."""
        if not self._file:
            return False
        try:
            return self._file.tell() >= self._max_bytes
        except OSError:
            return False

    def _rotate(self, path: str) -> None:
        """Rename current file to .1, .2, etc."""
        counter = 1
        while os.path.exists(f"{path}.{counter}"):
            counter += 1
        try:
            os.rename(path, f"{path}.{counter}")
        except OSError:
            pass

    def _close(self) -> None:
        if self._file:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

    def close(self) -> None:
        self._close()
        super().close()
