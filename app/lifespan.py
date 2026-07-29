import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.security.permission_registry import sync_permission_registry
from app.platform.audit.queue import start_operation_audit_queue, stop_operation_audit_queue
from app.platform.cache.redis import close_redis, init_redis
from app.platform.config.apply import apply_all_config
from app.platform.config.reader import config_reader
from app.platform.config.sync import start_config_sync_listener, stop_config_sync_listener
from app.platform.db.session import close_engine, init_engine
from app.platform.events import emit
from app.platform.http.client import close_http_client, init_http_client
from app.platform.module import (
    load_module_specs,
    run_event_handlers,
    run_shutdown_hooks,
    run_startup_hooks,
)
from app.platform.module.config_loader import load_module_configs
from app.platform.module.services import register_services
from app.platform.observability.tracing import shutdown_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lifespan startup: app.routes count = %d", len(app.routes))

    module_specs = load_module_specs()

    init_engine()
    await init_redis()
    await start_operation_audit_queue()

    await config_reader.load_all()
    apply_all_config()
    await start_config_sync_listener()
    load_module_configs(module_specs)
    await run_event_handlers(module_specs)

    register_services(module_specs)
    await sync_permission_registry(app)
    await init_http_client()

    await run_startup_hooks(module_specs)
    await emit("on_db_ready")

    try:
        yield
    finally:
        await run_shutdown_hooks(module_specs)
        await stop_config_sync_listener()
        await stop_operation_audit_queue()
        await close_http_client()
        await close_redis()
        await close_engine()
        shutdown_tracing()
