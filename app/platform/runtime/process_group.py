from __future__ import annotations

import asyncio
import os
import signal
import sys


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _worker_command() -> list[str]:
    command = [
        "celery",
        "-A",
        "app.worker.main:celery_app",
        "worker",
    ]
    if _env_bool("CELERY__WORKER_WITHOUT_MINGLE", True):
        command.append("--without-mingle")
    if _env_bool("CELERY__WORKER_WITHOUT_GOSSIP", True):
        command.append("--without-gossip")
    queues = _env("CELERY__WORKER_QUEUES", "judge,default")
    hostname = _env("HOSTNAME", "") or "local"
    nodename = _env("ACOJ_CELERY_NODENAME") or _env("CELERY_NODENAME") or f"judge@{hostname}"
    command.extend(
        [
            "-n",
            nodename,
            "--pool",
            _env("CELERY__WORKER_POOL", "threads"),
            "--concurrency",
            _env("CELERY__WORKER_CONCURRENCY", "8"),
            "-Q",
            queues,
            "--loglevel",
            _env("CELERY__WORKER_LOG_LEVEL", "INFO"),
        ]
    )
    return command


def _beat_command() -> list[str]:
    return [
        "celery",
        "-A",
        "app.worker.main:celery_app",
        "beat",
        "--loglevel",
        _env("CELERY__BEAT_LOG_LEVEL", "INFO"),
        "--scheduler",
        "redbeat.RedBeatScheduler",
    ]


def _api_command() -> list[str]:
    return ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]


async def _terminate(processes: dict[str, asyncio.subprocess.Process]) -> None:
    timeout = float(_env("APP__PROCESS_SHUTDOWN_TIMEOUT_SECONDS", "20"))
    for process in processes.values():
        if process.returncode is None:
            process.terminate()

    try:
        await asyncio.wait_for(
            asyncio.gather(*(process.wait() for process in processes.values())),
            timeout=timeout,
        )
    except TimeoutError:
        for process in processes.values():
            if process.returncode is None:
                process.kill()
        await asyncio.gather(*(process.wait() for process in processes.values()))


async def run_all() -> int:
    commands = {
        "worker": _worker_command(),
        "beat": _beat_command(),
        "api": _api_command(),
    }
    processes: dict[str, asyncio.subprocess.Process] = {}
    try:
        for name, command in commands.items():
            processes[name] = await asyncio.create_subprocess_exec(*command)
    except BaseException:
        await _terminate(processes)
        raise

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopping.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_: stopping.set())

    wait_tasks = {
        asyncio.create_task(process.wait()): name for name, process in processes.items()
    }
    stop_task = asyncio.create_task(stopping.wait())
    done, pending = await asyncio.wait(
        [*wait_tasks.keys(), stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 143 if stop_task in done else 1
    for task in done:
        name = wait_tasks.get(task)
        if name is not None:
            exit_code = task.result()
            print(f"{name} exited with status {exit_code}", file=sys.stderr)
            break

    await _terminate(processes)

    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    return exit_code


def main() -> None:
    raise SystemExit(asyncio.run(run_all()))


if __name__ == "__main__":
    main()
