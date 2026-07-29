from __future__ import annotations

from dataclasses import dataclass

from app.core.config.enums import StorageProvider
from app.core.config.settings import settings


@dataclass(frozen=True, slots=True)
class StorageConfig:
    id: str
    name: str
    provider: StorageProvider
    bucket: str = ""
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    region: str = ""
    use_ssl: bool = False
    base_url: str = ""
    public_path: str = "/api/v1/files"
    local_root: str = "storage"
    is_default: bool = False
    presign_expire_seconds: int = 3600


def fallback_storage_config() -> StorageConfig:
    """Build a startup/test fallback from environment settings."""
    return StorageConfig(
        id="__settings__",
        name="settings",
        provider=StorageProvider(settings.storage.provider),
        bucket=settings.storage.bucket or "",
        endpoint=settings.storage.endpoint or "",
        access_key=settings.storage.access_key or "",
        secret_key=settings.storage.secret_key or "",
        region=settings.storage.region or "",
        use_ssl=settings.storage.use_ssl,
        base_url=settings.storage.base_url or "",
        public_path=settings.storage.public_path or "/api/v1/files",
        local_root=settings.storage.local_root or "storage",
        is_default=True,
        presign_expire_seconds=settings.storage.presign_expire_seconds,
    )
