from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.enums import AccountStatusEnum, AccountType
from app.core.config.settings import settings
from app.core.exceptions.business import AuthenticationError, AuthorizationError
from app.core.network.client_ip import get_client_ip
from app.core.security.account_type import assert_account_type_allowed
from app.core.security.permission import PermissionChecker
from app.core.security.permission_registry import ACCOUNT_TYPE_META_ATTR, PERMISSION_META_ATTR
from app.core.security.session import SessionPayload, session_store
from app.deps.context import account_id_ctx, account_type_ctx
from app.deps.db import get_db_session
from app.platform.interfaces import resolve
from app.platform.interfaces.account_lookup import AccountLookupProtocol


async def get_current_session(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> SessionPayload:
    """从请求头读取原始 token，加载对应登录会话并进行安全校验。"""
    if not authorization:
        raise AuthenticationError("Missing authorization token")
    token = authorization.strip()
    session = await session_store.get(token)
    if not session:
        raise AuthenticationError("Invalid or expired token")

    # IP 绑定校验
    _validate_session_ip(request, session)

    # User-Agent 绑定校验
    _validate_session_user_agent(request, session)

    # 异步更新最后活跃时间（不阻塞调用链）
    _touch_session_background(token)

    account_id_ctx.set(session.account_id)
    account_type_ctx.set(session.account_type)
    return session


async def get_current_account(
    session: Annotated[SessionPayload, Depends(get_current_session)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    account_id_ctx.set(session.account_id)
    account_type_ctx.set(session.account_type)
    from typing import cast

    account = await cast(AccountLookupProtocol, resolve("account_lookup")).get_active_account_by_id(
        db, session.account_id
    )
    if (
        not account
        or account.cancelled_at is not None
        or account.account_status != AccountStatusEnum.ENABLED.value
    ):
        raise AuthenticationError("Account is inactive or missing")
    return account


def require_account_type(*account_types: AccountType):
    """基于账户类型枚举生成依赖校验函数。"""

    async def dependency(
        session: Annotated[SessionPayload, Depends(get_current_session)],
        account=Depends(get_current_account),
    ) -> SessionPayload:
        assert_account_type_allowed(session.account_type, set(account_types))
        return session

    setattr(
        dependency,
        ACCOUNT_TYPE_META_ATTR,
        {"account_types": [account_type.value for account_type in account_types]},
    )
    return dependency


def require_permission(permission_code: str):
    async def dependency(
        session: Annotated[SessionPayload, Depends(get_current_session)],
        account=Depends(get_current_account),
    ) -> SessionPayload:
        if not PermissionChecker.has_permission(session.permission_keys, permission_code):
            raise AuthorizationError(f"Permission denied: {permission_code}")
        return session

    setattr(dependency, PERMISSION_META_ATTR, {"permission_key": permission_code})
    return dependency


def _validate_session_ip(request: Request, session: SessionPayload) -> None:
    """如果启用了 IP 绑定且会话有 IP 记录，校验请求来源 IP 是否匹配。"""
    if not settings.auth.session_bind_ip:
        return
    session_ip = session.client_ip
    if not session_ip:
        return
    current_ip = get_client_ip(request)
    if current_ip and current_ip != session_ip:
        raise AuthenticationError("Session IP mismatch — token may have been stolen")


def _validate_session_user_agent(request: Request, session: SessionPayload) -> None:
    """如果启用了 UA 绑定且会话有 UA 记录，校验请求 User-Agent 是否匹配。"""
    if not settings.auth.session_bind_user_agent:
        return
    session_ua = session.user_agent
    if not session_ua:
        return
    current_ua = request.headers.get("user-agent")
    if current_ua and current_ua != session_ua:
        raise AuthenticationError("Session User-Agent mismatch")


def _touch_session_background(token: str) -> None:
    """在后台异步更新会话活跃时间，不引入额外 await 阻塞。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(session_store.touch(token))
    except RuntimeError:
        pass
