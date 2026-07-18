from enum import StrEnum


class AccountType(StrEnum):
    """
    账户类型
    """

    ADMIN = "ADMIN"  # 管理后台
    PORTAL = "PORTAL"  # 前台
    # 下面的账户类型待定
    # APP = "APP"
    # MERCHANT = "MERCHANT"
    # PARTNER = "PARTNER"


class DataScope(StrEnum):
    """
    数据范围
    """

    ALL = "ALL"  # 全部
    DEPT_AND_CHILD = "DEPT_AND_CHILD"  # 部门及子部门
    DEPT = "DEPT"  # 部门
    SELF = "SELF"  # 本人
    CUSTOM = "CUSTOM"  # 自定义


class StatusEnum(StrEnum):
    """
    状态
    """

    ENABLED = "ENABLED"  # 启用
    DISABLED = "DISABLED"  # 禁用


class AccountStatusEnum(StrEnum):
    """
    账户状态
    """

    ENABLED = "ENABLED"  # 启用
    DISABLED = "DISABLED"  # 禁用
    CANCELLED = "CANCELLED"  # 注销


class SysBizCategory(StrEnum):
    """
    系统/业务分类
    """

    SYS = "SYS"  # 系统
    BIZ = "BIZ"  # 业务


class StorageProvider(StrEnum):
    """
    文件存储服务商
    """

    LOCAL = "local"  # 本地存储
    MINIO = "minio"  # MinIO
    S3 = "s3"  # Amazon S3
    OSS = "oss"  # 阿里云 OSS
