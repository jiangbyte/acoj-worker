import json
from dataclasses import asdict

from app.core.config.enums import StorageProvider
from app.platform.storage.config import StorageConfig


class ConfigReader:
    """In-memory config snapshot. Storage comes from Settings / STORAGE__* env."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._storage_configs: dict[str, StorageConfig] = {}
        self._default_storage_id: str | None = None
        self._version = 0

    async def load_all(self) -> None:
        """Refresh snapshot version (env-backed storage via Settings fallback)."""
        self._version += 1

    async def reload(self) -> None:
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


config_reader = ConfigReader()
