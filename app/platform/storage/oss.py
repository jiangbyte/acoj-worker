from typing import Any
from urllib.parse import urljoin

from app.platform.storage.config import StorageConfig
from app.platform.storage.url import quote_object_name


class OSSStorage:
    def __init__(self, config: StorageConfig) -> None:
        import oss2

        self.config = config
        endpoint = config.endpoint.rstrip("/")
        auth = oss2.Auth(config.access_key, config.secret_key)
        self.bucket_name = config.bucket
        self.bucket = oss2.Bucket(auth, endpoint, self.bucket_name)

    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        headers = {"Content-Type": content_type}
        self.bucket.put_object(object_name, content, headers=headers)
        return self.get_object_url(object_name)

    def download_bytes(self, object_name: str) -> bytes:
        result = self.bucket.get_object(object_name)
        return result.read()

    def head_object(self, object_name: str) -> dict[str, Any] | None:
        import oss2

        try:
            meta = self.bucket.head_object(object_name)
        except oss2.exceptions.NoSuchKey:
            return None
        except oss2.exceptions.OssError as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise
        etag = str(getattr(meta, "etag", "") or "").strip('"')
        content_length = int(getattr(meta, "content_length", 0) or 0)
        return {"etag": etag, "content_length": content_length}

    def delete_object(self, object_name: str) -> None:
        self.bucket.delete_object(object_name)

    def get_object_url(self, object_name: str) -> str:
        if self.config.base_url:
            return urljoin(self.config.base_url.rstrip("/") + "/", quote_object_name(object_name))
        return self.get_presigned_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        return str(
            self.bucket.sign_url(
                "GET",
                object_name,
                self.config.presign_expire_seconds,
            )
        )
