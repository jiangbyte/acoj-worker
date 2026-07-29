import json
from dataclasses import asdict

from sqlalchemy import select

from app.core.config.enums import StorageProvider
from app.platform.config.crypto import decrypt_config_value, decrypt_storage_value
from app.platform.db.models.sys_config import SysConfig
from app.platform.db.models.sys_storage_config import SysStorageConfig
from app.platform.db.session import get_session_factory
from app.platform.storage.config import StorageConfig


class ConfigReader:
    """系统配置读取器，启动时从 DB 全量加载配置到不可变快照。"""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._storage_configs: dict[str, StorageConfig] = {}
        self._default_storage_id: str | None = None
        self._version = 0

    async def load_all(self) -> None:
        """从 DB 全量加载配置到内存缓存，成功后原子替换当前快照。"""
        cache: dict[str, str] = {}
        storage_configs: dict[str, StorageConfig] = {}
        default_storage_id: str | None = None
        factory = get_session_factory()
        async with factory() as db:
            async with db as session:
                stmt = select(SysConfig).where(SysConfig.config_value.isnot(None))
                rows = (await session.execute(stmt)).scalars().all()
                for row in rows:
                    cache[row.config_key] = decrypt_config_value(row.config_key, row.config_value)
                storage_stmt = select(SysStorageConfig).order_by(
                    SysStorageConfig.is_default.desc(),
                    SysStorageConfig.sort_code.asc(),
                    SysStorageConfig.name.asc(),
                )
                storage_rows = (await session.execute(storage_stmt)).scalars().all()
                presign_expire_seconds = _coerce_int(
                    cache.get("storage.presign_expire_seconds"),
                    3600,
                )
                for row in storage_rows:
                    config = _storage_config_from_row(row, presign_expire_seconds)
                    storage_configs[config.id] = config
                    if config.is_default and default_storage_id is None:
                        default_storage_id = config.id
        self._cache = cache
        self._storage_configs = storage_configs
        self._default_storage_id = default_storage_id
        self._version += 1

    async def reload(self) -> None:
        """重新加载（管理后台修改配置后调用）。"""
        await self.load_all()
        from app.platform.config.apply import apply_sys_config
        from app.platform.storage.manager import clear_storage_cache

        apply_sys_config()
        clear_storage_cache()

    @property
    def version(self) -> int:
        return self._version

    def get_default_storage(self) -> StorageConfig | None:
        if self._default_storage_id is None:
            return None
        return self._storage_configs.get(self._default_storage_id)

    def get_storage_config(self, config_id: str | None = None) -> StorageConfig | None:
        if config_id is None:
            return self.get_default_storage()
        return self._storage_configs.get(config_id)

    def get_storage_config_by_provider(
        self,
        provider: str | StorageProvider,
    ) -> StorageConfig | None:
        provider_value = StorageProvider(provider)
        for config in self._storage_configs.values():
            if config.provider == provider_value:
                return config
        return None

    def list_storage_configs(self) -> list[StorageConfig]:
        return list(self._storage_configs.values())

    def get_active_storage(self) -> dict | None:
        active = self.get_default_storage()
        return asdict(active) if active else None

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._cache.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self._cache.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._cache.get(key)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes")

    def get_list(self, key: str, default: list[str] | None = None) -> list[str]:
        val = self._cache.get(key)
        if val is None:
            return default or []
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
            return default or []
        except (json.JSONDecodeError, TypeError):
            return default or []

    def raw_items(self) -> dict[str, str]:
        return dict(self._cache)


def _storage_config_from_row(row: SysStorageConfig, presign_expire_seconds: int) -> StorageConfig:
    return StorageConfig(
        id=row.id,
        name=row.name,
        provider=StorageProvider(row.provider),
        bucket=decrypt_storage_value("bucket", row.bucket) or "",
        endpoint=decrypt_storage_value("endpoint", row.endpoint) or "",
        access_key=decrypt_storage_value("access_key", row.access_key) or "",
        secret_key=decrypt_storage_value("secret_key", row.secret_key) or "",
        region=decrypt_storage_value("region", row.region) or "",
        use_ssl=bool(row.use_ssl),
        base_url=decrypt_storage_value("base_url", row.base_url) or "",
        public_path=row.public_path or "/api/v1/files",
        local_root=row.local_root or "storage",
        is_default=bool(row.is_default),
        presign_expire_seconds=presign_expire_seconds,
    )


def _coerce_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


config_reader = ConfigReader()
