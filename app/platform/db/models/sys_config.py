"""系统配置表模型 — ORM 定义在 platform 层供框架基础设施查询。"""
from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin
from app.platform.id_generator.snowflake import generate_snowflake_id


class SysConfig(Base, TimestampMixin):
    """系统配置表，维护后台可配置键值数据。"""

    __tablename__ = "sys_config"
    __table_args__ = (
        Index("idx_sys_config_key", "config_key", unique=True),
        Index("idx_sys_config_category", "category"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_snowflake_id,
        comment="主键",
    )
    config_key: Mapped[str] = mapped_column(String(255), nullable=False, comment="配置键")
    config_value: Mapped[str | None] = mapped_column(Text, comment="配置值")
    category: Mapped[str | None] = mapped_column(String(255), comment="分类")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    sort_code: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序码")
    ext_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="扩展信息")
