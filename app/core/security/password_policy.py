"""Password policy enforcement — strength validation and common-password
checking, mirroring the等保 password-complexity requirements.

All policy parameters are driven through ``settings.password_policy``.
"""
import re

from app.core.config.settings import settings
from app.core.exceptions.business import BusinessError


# fmt: off
_COMMON_PASSWORDS: frozenset[str] = frozenset({
    "123456", "password", "12345678", "qwerty", "123456789",
    "12345", "1234", "111111", "1234567", "sunshine",
    "qwerty123", "iloveyou", "princess", "admin", "welcome",
    "666666", "abc123", "football", "123123", "monkey",
    "654321", "!@#$%^&*", "charlie", "aa123456", "donald",
    "password1", "qwerty12345", "1234567890", "letmein", "password123",
    "admin123", "passw0rd", "hello123", "test123", "root",
    "administrator", "p@ssw0rd", "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "pass123", "password!", "default", "change123", "changeme",
})
# fmt: on


def validate_password_strength(password: str) -> None:
    """Validate password against the configured policy.

    Raises ``BusinessError`` with a user-facing message on the first
    violated rule.
    """
    policy = settings.password_policy

    if len(password) < policy.min_length:
        raise BusinessError(
            f"密码长度至少 {policy.min_length} 个字符"
        )
    if len(password) > policy.max_length:
        raise BusinessError(
            f"密码长度不能超过 {policy.max_length} 个字符"
        )

    if policy.require_uppercase and not re.search(r"[A-Z]", password):
        raise BusinessError("密码必须包含至少一个大写字母")

    if policy.require_lowercase and not re.search(r"[a-z]", password):
        raise BusinessError("密码必须包含至少一个小写字母")

    if policy.require_digit and not re.search(r"[0-9]", password):
        raise BusinessError("密码必须包含至少一个数字")

    if policy.require_special and not re.search(r"[^A-Za-z0-9]", password):
        raise BusinessError("密码必须包含至少一个特殊字符")

    if policy.common_password_check and password.lower() in _COMMON_PASSWORDS:
        raise BusinessError("密码过于常见，请更换")


def estimate_strength_level(password: str) -> int:
    """Return a rough strength score (0-4) for frontend display."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
        score += 1
    if re.search(r"[0-9]", password) and re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return min(score, 4)
