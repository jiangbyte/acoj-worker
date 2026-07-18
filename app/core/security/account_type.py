from collections.abc import Iterable

from app.core.config.enums import AccountType
from app.core.exceptions.business import AuthorizationError


def assert_account_type_allowed(
    actual_account_type: str,
    expected_account_types: Iterable[AccountType],
) -> None:
    """校验当前账户类型是否在允许访问的枚举范围内。"""
    if actual_account_type not in {account_type.value for account_type in expected_account_types}:
        raise AuthorizationError(f"Account type {actual_account_type!r} is not allowed")
