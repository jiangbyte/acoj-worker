from typing import Iterable

from app.core.config.enums import DataScope
from app.core.security.session import PermissionGrantPayload, SessionPayload
from app.platform.interfaces import resolve
from app.platform.interfaces.data_scope_resolver import DataScopeResolverProtocol


def find_permission_grant(
    session: SessionPayload,
    permission_key: str,
) -> PermissionGrantPayload | None:
    for grant in reversed(session.permission_grants):
        if grant["permission_key"] == permission_key:
            return grant
    return None


def has_unrestricted_data_scope(session: SessionPayload, permission_key: str) -> bool:
    if "*:*:*" in session.permission_keys:
        return True
    grant = find_permission_grant(session, permission_key)
    return bool(grant and DataScope(str(grant["data_scope"])) == DataScope.ALL)


async def resolve_data_scope_dept_ids(
    session: SessionPayload,
    permission_key: str,
) -> list[str] | None:
    if has_unrestricted_data_scope(session, permission_key):
        return None

    grant = find_permission_grant(session, permission_key)
    data_scope = DataScope(str(grant["data_scope"])) if grant else DataScope.SELF
    custom_scope_dept_ids = list(grant["custom_scope_dept_ids"]) if grant else []

    if data_scope == DataScope.ALL:
        return None
    if data_scope == DataScope.DEPT:
        return _unique_ids(session.dept_ids)
    if data_scope == DataScope.DEPT_AND_CHILD:
        return await list_dept_and_child_ids(session.dept_ids)
    if data_scope == DataScope.CUSTOM:
        return _unique_ids(custom_scope_dept_ids)
    return []


async def list_dept_and_child_ids(dept_ids: Iterable[str]) -> list[str]:
    from typing import cast

    return await cast(DataScopeResolverProtocol, resolve("data_scope_resolver")).list_dept_and_child_ids(
        dept_ids
    )


def _unique_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if value})
