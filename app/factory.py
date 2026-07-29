import logging

from fastapi import FastAPI

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
from app.middleware.operation_audit import OperationAuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.trace import TraceMiddleware
from app.platform.db.session import engine
from app.platform.module import load_module_specs
from app.platform.module.services import register_services
from app.platform.observability.manager import setup_observability

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()

    # 延迟导入：确保 setup_logging() 先配置好，模块发现的日志才能正常输出
    from app.api.router import router as api_router

    # Some test clients and embedding surfaces do not run ASGI lifespan.
    # Register service interfaces at construction time as well; startup re-registers them.
    register_services(load_module_specs())

    app = FastAPI(
        title=settings.app.name,
        debug=False,
        docs_url="/docs" if settings.swagger.enabled else None,
        redoc_url="/redoc" if settings.swagger.enabled else None,
        openapi_url="/openapi.json" if settings.swagger.enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(TraceMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(OperationAuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthContextMiddleware)
    add_cors(app)
    register_exception_handlers(app)
    customize_openapi_error_responses(app)
    setup_observability(app, engine=engine)

    @app.get("/", tags=["health"], response_model=RootHealthResponse)
    async def root() -> RootHealthResponse:
        return RootHealthResponse(status="ok", service=settings.app.name)

    app.include_router(api_router)
    logger.info("Application created with %d routes", len(app.routes))

    return app
