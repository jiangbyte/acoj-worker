from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import false, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config.enums import DataScope
from app.core.security.session import PermissionGrantPayload, SessionPayload
from app.platform.interfaces import resolve
from app.platform.interfaces.data_scope_resolver import DataScopeResolverProtocol


@dataclass(frozen=True, slots=True)
class DataScopeColumns:
    owner: ColumnElement[bool] | None = None
    dept: ColumnElement[bool] | None = None


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
    db: AsyncSession,
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
        return await list_dept_and_child_ids(db, session.dept_ids)
    if data_scope == DataScope.CUSTOM:
        return _unique_ids(custom_scope_dept_ids)
    return []


async def build_data_scope_filter(
    db: AsyncSession,
    session: SessionPayload,
    permission_key: str,
    *,
    owner_column=None,
    dept_column=None,
) -> ColumnElement[bool]:
    if has_unrestricted_data_scope(session, permission_key):
        return true()

    grant = find_permission_grant(session, permission_key)
    data_scope = DataScope(str(grant["data_scope"])) if grant else DataScope.SELF

    if data_scope == DataScope.SELF:
        return owner_column == session.account_id if owner_column is not None else false()

    dept_ids = await resolve_data_scope_dept_ids(db, session, permission_key)
    return _in_or_false(dept_column, dept_ids or [])


async def list_dept_and_child_ids(db: AsyncSession, dept_ids: Iterable[str]) -> list[str]:
    from typing import cast

    return await cast(DataScopeResolverProtocol, resolve("data_scope_resolver")).list_dept_and_child_ids(
        db, dept_ids
    )


def _in_or_false(column, values: Iterable[str]) -> ColumnElement[bool]:
    unique_values = _unique_ids(values)
    if column is None or not unique_values:
        return false()
    return column.in_(unique_values)


def _unique_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if value})
