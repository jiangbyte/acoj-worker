"""文件存储配置表模型 — ORM 定义在 platform 层供框架基础设施查询。"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin
from app.platform.id_generator.snowflake import generate_snowflake_id


class SysStorageConfig(Base, TimestampMixin):
    """文件存储配置表，支持多实例，仅 is_default=True 的为当前启用配置。"""

    __tablename__ = "sys_storage_config"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_snowflake_id,
        comment="主键",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="配置名称")
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="存储服务商：local/minio/s3/oss"
    )
    bucket: Mapped[str | None] = mapped_column(String(255), comment="存储桶")
    endpoint: Mapped[str | None] = mapped_column(String(500), comment="服务端点")
    access_key: Mapped[str | None] = mapped_column(String(255), comment="访问密钥 ID")
    secret_key: Mapped[str | None] = mapped_column(String(255), comment="访问密钥 Secret")
    region: Mapped[str | None] = mapped_column(String(100), comment="区域")
    use_ssl: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否使用 SSL 连接"
    )
    base_url: Mapped[str | None] = mapped_column(String(500), comment="自定义基础 URL")
    public_path: Mapped[str] = mapped_column(
        String(255), default="/api/v1/files", nullable=False, comment="公开访问路径"
    )
    local_root: Mapped[str] = mapped_column(
        String(500), default="storage", nullable=False, comment="本地存储根目录"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否为当前启用的默认配置（互斥）"
    )
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    sort_code: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序码")
