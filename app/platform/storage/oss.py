from urllib.parse import urljoin

from app.core.config.settings import settings
from app.platform.storage.url import quote_object_name


class OSSStorage:
    def __init__(self) -> None:
        import oss2

        endpoint = settings.storage.endpoint.rstrip("/")
        auth = oss2.Auth(settings.storage.access_key, settings.storage.secret_key)
        self.bucket_name = settings.storage.bucket
        self.bucket = oss2.Bucket(auth, endpoint, self.bucket_name)

    def upload_bytes(self, object_name: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        headers = {"Content-Type": content_type}
        self.bucket.put_object(object_name, content, headers=headers)
        return self.get_object_url(object_name)

    def download_bytes(self, object_name: str) -> bytes:
        result = self.bucket.get_object(object_name)
        return result.read()

    def head_object(self, object_name: str) -> dict | None:
        try:
            result = self.bucket.head_object(object_name)
            import oss2
            return {
                "etag": result.headers.get("etag", "").strip('"'),
                "size": result.content_length or 0,
                "last_modified": result.headers.get("last-modified"),
            }
        except oss2.exceptions.NoSuchKey:
            return None

    def delete_object(self, object_name: str) -> None:
        self.bucket.delete_object(object_name)

    def get_object_url(self, object_name: str) -> str:
        if settings.storage.base_url:
            return urljoin(settings.storage.base_url.rstrip("/") + "/", quote_object_name(object_name))
        return self.get_presigned_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        return str(
            self.bucket.sign_url(
                "GET",
                object_name,
                settings.storage.presign_expire_seconds,
            )
        )
