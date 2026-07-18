class PermissionChecker:
    @staticmethod
    def has_permission(permissions: list[str], permission_code: str) -> bool:
        return permission_code in permissions or "*:*:*" in permissions
