"""Operation audit middleware — extended to cover all admin/portal write operations."""
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.deps.context import (
    account_id_ctx,
    account_type_ctx,
    client_ip_ctx,
    request_id_ctx,
    user_agent_ctx,
)
from app.platform.audit.queue import OperationAuditEvent, operation_audit_queue

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Global audit path: covers all admin/portal write operations
AUDIT_PATH_RE = re.compile(
    r"^/api/v\d+/(?P<account_type>admin|portal)/"
    r"(?P<module_path>[a-z][a-z0-9/_-]*)"
    r"(?P<action>/[^?]*)?"
)

# Skip well-known public paths (these have dedicated audit or are noise)
SKIP_AUDIT_PATH_PATTERNS = (
    "/captcha",
    "/password-key",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/cancel",
    "/me",
)


def _should_skip_path(path: str) -> bool:
    path_lower = path.lower()
    for pattern in SKIP_AUDIT_PATH_PATTERNS:
        if path_lower.endswith(pattern):
            return True
    return False


def _extract_resource_type(module_path: str) -> str:
    parts = module_path.strip("/").split("/")
    resource = parts[-1] if parts else module_path
    resource = re.sub(r"[0-9a-f]{8,}", "", resource).strip("-_")
    return resource if resource else module_path.replace("/", "_")


def _extract_action(action_str: str | None, method: str) -> str:
    if not action_str:
        return method.lower()
    action = action_str.strip("/").split("/", 1)[0]
    return action.replace("-", "_") if action else method.lower()


class OperationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            audit_info = _match_audit_target(request)
            if audit_info is not None:
                resource_type, action = audit_info
                operation_audit_queue.enqueue(
                    OperationAuditEvent(
                        resource_type=resource_type,
                        action=action,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        account_id=account_id_ctx.get(),
                        account_type=account_type_ctx.get(),
                        request_id=request_id_ctx.get(),
                        ip=client_ip_ctx.get(),
                        user_agent=user_agent_ctx.get(),
                    )
                )
        except Exception:
            pass
        return response


def _match_audit_target(request: Request) -> tuple[str, str] | None:
    if request.method.upper() not in AUDIT_METHODS:
        return None
    path = request.url.path
    if _should_skip_path(path):
        return None
    match = AUDIT_PATH_RE.match(path)
    if not match:
        # Fallback: /api/v*/logout also logged
        if any(seg in path.split("/") for seg in ("logout",)):
            return ("account", "logout")
        return None

    module_path = match.group("module_path")
    action_str = match.group("action")
    resource_type = _extract_resource_type(module_path)
    action = _extract_action(action_str, request.method)
    return resource_type, action
