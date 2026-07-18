from app.core.config.enums import StorageProvider
from app.core.config.settings import settings
from app.platform.storage.local import LocalStorage
from app.platform.storage.oss import OSSStorage
from app.platform.storage.s3 import MinioStorage, S3Storage


def get_storage():
    """按配置返回当前存储实现。"""
    provider = StorageProvider(settings.storage.provider)
    if provider == StorageProvider.LOCAL:
        return LocalStorage(settings.storage.local_root)
    if provider == StorageProvider.MINIO:
        return MinioStorage()
    if provider == StorageProvider.S3:
        return S3Storage()
    if provider == StorageProvider.OSS:
        return OSSStorage()
    raise ValueError(f"Unsupported storage provider: {settings.storage.provider}")
