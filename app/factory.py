from fastapi import FastAPI
import logging

from app.core.config.settings import settings
from app.core.exceptions.handlers import (
    customize_openapi_error_responses,
    register_exception_handlers,
)
from app.core.logger.setup import setup_logging
from app.core.schema.health import RootHealthResponse
from app.lifespan import lifespan
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.auth_context import AuthContextMiddleware
from app.middleware.cors import add_cors
from app.middleware.trace import TraceMiddleware
from app.platform.db.session import engine
from app.platform.observability.manager import setup_observability

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()

    # 延迟导入：确保 setup_logging() 先配置好，模块发现的日志才能正常输出
    from app.api.router import router as api_router

    logger.info("create_app: api_router has %d routes", len(api_router.routes))

    app = FastAPI(
        title=settings.app.name,
        debug=False,
        docs_url="/docs" if settings.swagger.enabled else None,
        redoc_url="/redoc" if settings.swagger.enabled else None,
        openapi_url="/openapi.json" if settings.swagger.enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(TraceMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(AuthContextMiddleware)
    add_cors(app)
    register_exception_handlers(app)
    customize_openapi_error_responses(app)
    setup_observability(app, engine=engine)

    @app.get("/", tags=["health"], response_model=RootHealthResponse)
    async def root() -> RootHealthResponse:
        return RootHealthResponse(status="ok", service=settings.app.name)

    logger.info("create_app: app.routes before include_router = %d", len(app.routes))

    # 诊断：检查 api_router.routes 中的路由类型分布
    from collections import Counter
    route_types = Counter(type(r).__name__ for r in api_router.routes)
    logger.info("create_app: api_router route types: %s", dict(route_types))

    app.include_router(api_router)
    logger.info("create_app: app.routes after include_router = %d", len(app.routes))

    # 如果 include_router 没生效，尝试逐个添加
    if len(app.routes) < 10 and len(api_router.routes) > 10:
        logger.warning(
            "include_router only added %d routes, expected ~%d. Attempting direct route injection.",
            len(app.routes) - 5,
            len(api_router.routes),
        )
        for route in api_router.routes:
            app.routes.append(route)
        logger.info("create_app: app.routes after direct injection = %d", len(app.routes))

    return app
