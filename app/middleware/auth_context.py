from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.deps.context import account_id_ctx, account_type_ctx, duration_ms_ctx, status_code_ctx


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        account_token = account_id_ctx.set(None)
        account_type_token = account_type_ctx.set(None)
        status_token = status_code_ctx.set(None)
        duration_token = duration_ms_ctx.set(None)
        try:
            return await call_next(request)
        finally:
            account_id_ctx.reset(account_token)
            account_type_ctx.reset(account_type_token)
            status_code_ctx.reset(status_token)
            duration_ms_ctx.reset(duration_token)
