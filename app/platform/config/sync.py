from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Thread

from app.core.config.settings import settings
from app.platform.cache.redis import get_redis
from app.platform.config.reader import config_reader

logger = logging.getLogger(__name__)

CONFIG_SYNC_CHANNEL = "hei:config:changed"

_instance_id = uuid.uuid4().hex
_listener_task: asyncio.Task | None = None
_pubsub = None
_last_event_at: str | None = None
_last_error: str | None = None
_listener_thread: Thread | None = None
_listener_thread_loop: asyncio.AbstractEventLoop | None = None
_listener_thread_task: asyncio.Task | None = None


@dataclass(slots=True)
class ConfigSyncState:
    enabled: bool
    running: bool
    channel: str
    last_event_at: str | None = None
    last_error: str | None = None


async def reload_and_publish(reason: str) -> bool:
    """Reload this process and publish a best-effort invalidation event to peers."""
    await config_reader.reload()
    return await publish_config_changed(reason)


async def publish_config_changed(reason: str) -> bool:
    redis = get_redis()
    if redis is None:
        _set_error("redis not initialized")
        logger.warning("Config changed locally but Redis is unavailable; peers were not notified")
        return False

    payload = {
        "source": _instance_id,
        "reason": reason,
        "version": config_reader.version,
        "at": datetime.now(UTC).isoformat(),
    }
    try:
        await redis.publish(CONFIG_SYNC_CHANNEL, json.dumps(payload, ensure_ascii=True))
        _set_error(None)
        return True
    except Exception as exc:
        _set_error(exc.__class__.__name__)
        logger.warning("Failed to publish config change event", exc_info=True)
        return False


async def start_config_sync_listener() -> None:
    global _listener_task
    if _listener_task is not None and not _listener_task.done():
        return
    redis = get_redis()
    if redis is None:
        _set_error("redis not initialized")
        logger.warning("Config sync listener not started because Redis is unavailable")
        return
    _listener_task = asyncio.create_task(_listen(redis), name="config-sync-listener")


async def stop_config_sync_listener() -> None:
    global _listener_task, _pubsub
    if _listener_task is not None:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass
        _listener_task = None
    if _pubsub is not None:
        try:
            await _pubsub.unsubscribe(CONFIG_SYNC_CHANNEL)
        except Exception:
            logger.debug("Failed to unsubscribe config sync pubsub", exc_info=True)
        await _close_pubsub()


def start_config_sync_listener_thread() -> None:
    """Start config sync in a dedicated loop for Celery worker processes."""
    global _listener_thread
    if _listener_thread is not None and _listener_thread.is_alive():
        return
    _listener_thread = Thread(
        target=_run_listener_thread,
        name="config-sync-listener",
        daemon=True,
    )
    _listener_thread.start()


def stop_config_sync_listener_thread(timeout: float = 5.0) -> None:
    global _listener_thread, _listener_thread_loop, _listener_thread_task
    if _listener_thread_loop is not None and _listener_thread_task is not None:
        _listener_thread_loop.call_soon_threadsafe(_listener_thread_task.cancel)
    if _listener_thread is not None:
        _listener_thread.join(timeout=timeout)
    _listener_thread = None
    _listener_thread_loop = None
    _listener_thread_task = None


def get_config_sync_state() -> ConfigSyncState:
    redis = get_redis()
    running = _listener_task is not None and not _listener_task.done()
    thread_running = _listener_thread is not None and _listener_thread.is_alive()
    return ConfigSyncState(
        enabled=redis is not None or thread_running,
        running=running or thread_running,
        channel=CONFIG_SYNC_CHANNEL,
        last_event_at=_last_event_at,
        last_error=_last_error,
    )


async def _listen(redis) -> None:
    global _pubsub, _last_event_at
    while True:
        _pubsub = redis.pubsub()
        try:
            await _pubsub.subscribe(CONFIG_SYNC_CHANNEL)
            logger.info("Config sync listener started on channel %s", CONFIG_SYNC_CHANNEL)
            while True:
                message = await _pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                event = _decode_event(message.get("data"))
                if not event or event.get("source") == _instance_id:
                    continue
                await config_reader.reload()
                _last_event_at = datetime.now(UTC).isoformat()
                _set_error(None)
                logger.info(
                    "Reloaded config from distributed event reason=%s version=%s",
                    event.get("reason"),
                    event.get("version"),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _set_error(exc.__class__.__name__)
            logger.warning("Config sync listener reconnecting after failure", exc_info=True)
            await asyncio.sleep(5)
        finally:
            await _close_pubsub()


def _decode_event(raw: object) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return None
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _set_error(value: str | None) -> None:
    global _last_error
    _last_error = value


async def _close_pubsub() -> None:
    global _pubsub
    if _pubsub is None:
        return
    try:
        close = getattr(_pubsub, "aclose", None) or getattr(_pubsub, "close", None)
        if close is not None:
            await close()
    except Exception:
        logger.debug("Failed to close config sync pubsub", exc_info=True)
    _pubsub = None


def _run_listener_thread() -> None:
    global _listener_thread_loop, _listener_thread_task
    loop = asyncio.new_event_loop()
    _listener_thread_loop = loop
    asyncio.set_event_loop(loop)
    _listener_thread_task = loop.create_task(_listen_with_dedicated_redis())
    try:
        loop.run_until_complete(_listener_thread_task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


async def _listen_with_dedicated_redis() -> None:
    from redis.asyncio import Redis

    redis = Redis.from_url(
        settings.redis.url,
        decode_responses=False,
        max_connections=2,
    )
    try:
        await redis.ping()
        await _listen(redis)
    finally:
        await redis.aclose()
