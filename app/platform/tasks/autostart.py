from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from app.core.config.settings import PROJECT_ROOT, settings
from app.platform.observability.metrics import set_celery_beat_lock_state, set_celery_process_state

logger = logging.getLogger(__name__)

CELERY_APP_PATH = "app.worker.main:celery_app"


class CeleryProcessManager:
    def __init__(self) -> None:
        self._processes: list[tuple[str, subprocess.Popen[bytes]]] = []
        self._beat_lock_owner = uuid.uuid4().hex
        self._beat_lock_client = None
        self._beat_lock_stop = threading.Event()
        self._beat_lock_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._processes:
            return
        if not settings.celery.auto_start_enabled:
            logger.info("Skip Celery auto start because it is disabled")
            return
        if not settings.celery.broker_url:
            logger.info("Skip Celery auto start because broker url is empty")
            return

        runtime_dir = PROJECT_ROOT / ".runtime"
        runtime_dir.mkdir(exist_ok=True)
        env = os.environ.copy()

        if settings.celery.auto_start_worker_enabled:
            self._start_process("celery-worker", self._worker_command(), env)
        if settings.celery.auto_start_beat_enabled and self._acquire_beat_lock():
            self._start_process("celery-beat", self._beat_command(runtime_dir), env)

    def status(self) -> dict[str, object]:
        return {
            "processes": {
                name: process.poll() is None
                for name, process in self._processes
            },
            "beat_lock_held": self._beat_lock_client is not None,
        }

    async def stop(self) -> None:
        if not self._processes:
            self._release_beat_lock()
            return

        timeout = settings.celery.shutdown_timeout_seconds
        for name, process in self._processes:
            if process.poll() is None:
                logger.info("Stopping %s process", name, extra={"pid": process.pid})
                self._terminate_process(process)

        for name, process in self._processes:
            try:
                await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=timeout)
            except TimeoutError:
                logger.warning("Killing %s process after shutdown timeout", name)
                self._kill_process(process)
                await asyncio.to_thread(process.wait)

        for name, _process in self._processes:
            set_celery_process_state(name, False)
        self._processes.clear()
        self._release_beat_lock()

    def _start_process(self, name: str, command: list[str], env: dict[str, str]) -> None:
        kwargs: dict[str, object] = {
            "cwd": PROJECT_ROOT,
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid

        process = subprocess.Popen(command, **kwargs)
        self._processes.append((name, process))
        set_celery_process_state(name, True)
        logger.info("Started %s process", name, extra={"pid": process.pid})

    def _worker_command(self) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "celery",
            "-A",
            CELERY_APP_PATH,
            "worker",
        ]
        if settings.celery.worker_without_mingle:
            command.append("--without-mingle")
        if settings.celery.worker_without_gossip:
            command.append("--without-gossip")
        command.extend(
            [
                "--loglevel",
                settings.celery.worker_log_level,
            ]
        )
        if settings.celery.worker_pool:
            command.extend(["--pool", settings.celery.worker_pool])
        if settings.celery.worker_concurrency > 0:
            command.extend(["--concurrency", str(settings.celery.worker_concurrency)])
        return command

    def _beat_command(self, runtime_dir: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "celery",
            "-A",
            CELERY_APP_PATH,
            "beat",
            "--loglevel",
            settings.celery.beat_log_level,
            "--schedule",
            str(runtime_dir / "celerybeat-schedule"),
        ]

    def _terminate_process(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            process.terminate()
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return

    def _kill_process(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            process.kill()
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            return

    def _acquire_beat_lock(self) -> bool:
        try:
            import redis

            client = redis.Redis.from_url(settings.redis.url, decode_responses=True)
            acquired = bool(
                client.set(
                    settings.celery.beat_lock_key,
                    self._beat_lock_owner,
                    nx=True,
                    ex=settings.celery.beat_lock_ttl_seconds,
                )
            )
        except Exception:
            logger.exception("Failed to acquire Celery beat lock")
            if settings.app.debug:
                logger.warning(
                    "Starting Celery beat without Redis lock because app debug is enabled"
                )
                set_celery_beat_lock_state(False)
                return True
            set_celery_beat_lock_state(False)
            return False
        if not acquired:
            logger.info("Skip Celery beat auto start because another instance holds the lock")
            set_celery_beat_lock_state(False)
            return False
        self._beat_lock_client = client
        self._start_beat_lock_renewal()
        set_celery_beat_lock_state(True)
        return True

    def _start_beat_lock_renewal(self) -> None:
        self._beat_lock_stop.clear()
        self._beat_lock_thread = threading.Thread(
            target=self._renew_beat_lock_loop,
            name="celery-beat-lock-renewal",
            daemon=True,
        )
        self._beat_lock_thread.start()

    def _renew_beat_lock_loop(self) -> None:
        while not self._beat_lock_stop.wait(settings.celery.beat_lock_renew_seconds):
            try:
                if self._beat_lock_client is None:
                    return
                current_owner = self._beat_lock_client.get(settings.celery.beat_lock_key)
                if current_owner != self._beat_lock_owner:
                    logger.warning("Lost Celery beat lock; stopping renewal")
                    set_celery_beat_lock_state(False)
                    return
                self._beat_lock_client.expire(
                    settings.celery.beat_lock_key,
                    settings.celery.beat_lock_ttl_seconds,
                )
            except Exception:
                logger.exception("Failed to renew Celery beat lock")

    def _release_beat_lock(self) -> None:
        self._beat_lock_stop.set()
        if self._beat_lock_thread and self._beat_lock_thread.is_alive():
            self._beat_lock_thread.join(timeout=1)
        try:
            if self._beat_lock_client is not None:
                script = """
                if redis.call("GET", KEYS[1]) == ARGV[1] then
                    return redis.call("DEL", KEYS[1])
                end
                return 0
                """
                self._beat_lock_client.eval(
                    script,
                    1,
                    settings.celery.beat_lock_key,
                    self._beat_lock_owner,
                )
                self._beat_lock_client.close()
        except Exception:
            logger.debug("Failed to release Celery beat lock", exc_info=True)
        finally:
            self._beat_lock_client = None
            self._beat_lock_thread = None
            set_celery_beat_lock_state(False)


celery_process_manager = CeleryProcessManager()
