from threading import RLock

from app.core.config.enums import StorageProvider
from app.platform.config.reader import config_reader
from app.platform.storage.config import StorageConfig, fallback_storage_config
from app.platform.storage.local import LocalStorage
from app.platform.storage.oss import OSSStorage
from app.platform.storage.s3 import MinioStorage, S3Storage

_storage_cache: dict[tuple[int, StorageConfig], object] = {}
_storage_cache_lock = RLock()


def clear_storage_cache() -> None:
    with _storage_cache_lock:
        _storage_cache.clear()


def get_storage(
    config_id: str | None = None,
    *,
    provider: StorageProvider | str | None = None,
    allow_settings_fallback: bool = True,
):
    """Return a storage client for a cached DB storage config."""
    config = resolve_storage_config(
        config_id=config_id,
        provider=provider,
        allow_settings_fallback=allow_settings_fallback,
    )
    cache_key = (config_reader.version, config)
    with _storage_cache_lock:
        storage = _storage_cache.get(cache_key)
        if storage is None:
            storage = _build_storage(config)
            _storage_cache[cache_key] = storage
        return storage


def resolve_storage_config(
    config_id: str | None = None,
    *,
    provider: StorageProvider | str | None = None,
    allow_settings_fallback: bool = True,
) -> StorageConfig:
    config: StorageConfig | None = None
    explicit_config_id = bool(config_id) and config_id != "__settings__"
    if config_id:
        config = config_reader.get_storage_config(config_id)
        if config is None:
            try:
                provider = StorageProvider(config_id)
                explicit_config_id = False
            except ValueError:
                pass
    if config is None and provider is not None:
        config = config_reader.get_storage_config_by_provider(StorageProvider(provider))
    if config is None and config_id is None and provider is None:
        config = config_reader.get_default_storage()
    if config is None and allow_settings_fallback and not explicit_config_id:
        config = fallback_storage_config()
    if config is None:
        raise RuntimeError("Storage config is not available")
    return config


def _build_storage(config: StorageConfig):
    if config.provider == StorageProvider.LOCAL:
        return LocalStorage(config)
    if config.provider == StorageProvider.MINIO:
        return MinioStorage(config)
    if config.provider == StorageProvider.S3:
        return S3Storage(config)
    if config.provider == StorageProvider.OSS:
        return OSSStorage(config)
    raise ValueError(f"Unsupported storage provider: {config.provider}")
