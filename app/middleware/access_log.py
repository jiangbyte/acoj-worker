import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.deps.context import duration_ms_ctx, status_code_ctx
from app.platform.observability.metrics import track_http_request

logger = logging.getLogger("access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        with track_http_request(request.method, request.url.path) as finalize:
            response = await call_next(request)
            cost_ms = round((time.perf_counter() - start) * 1000, 2)
            duration_ms_ctx.set(cost_ms)
            status_code_ctx.set(response.status_code)
            finalize(response.status_code)
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": cost_ms,
            },
        )
        return response
