import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.deps.context import (
    client_ip_ctx,
    request_id_ctx,
    request_method_ctx,
    request_path_ctx,
    span_id_ctx,
    trace_id_ctx,
    user_agent_ctx,
)
from app.platform.observability.tracing import sync_trace_context


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex)
        request_token = request_id_ctx.set(request_id)
        path_token = request_path_ctx.set(request.url.path)
        method_token = request_method_ctx.set(request.method)
        ip_token = client_ip_ctx.set(_client_ip(request))
        user_agent_token = user_agent_ctx.set(request.headers.get("user-agent"))
        try:
            sync_trace_context()
            response = await call_next(request)
        finally:
            request_id_ctx.reset(request_token)
            request_path_ctx.reset(path_token)
            request_method_ctx.reset(method_token)
            client_ip_ctx.reset(ip_token)
            user_agent_ctx.reset(user_agent_token)
            trace_id_ctx.set(None)
            span_id_ctx.set(None)
        response.headers["X-Request-Id"] = request_id
        return response


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else None
