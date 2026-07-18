from urllib.parse import urljoin

import boto3
from botocore.client import Config

from app.core.config.settings import settings
from app.platform.storage.url import quote_object_name


class S3CompatibleStorage:
    def __init__(self, *, force_path_style: bool = False) -> None:
        self.bucket = settings.storage.bucket
        endpoint = settings.storage.endpoint.rstrip("/")
        scheme = "https" if settings.storage.use_ssl else "http"
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            endpoint_url = endpoint
        else:
            endpoint_url = f"{scheme}://{endpoint}"
        config_kwargs = {"signature_version": "s3v4"}
        if force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}
        config = Config(**config_kwargs)
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.storage.access_key,
            aws_secret_access_key=settings.storage.secret_key,
            region_name=settings.storage.region,
            config=config,
        )

    def upload_bytes(self, object_name: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=object_name, Body=content, ContentType=content_type)
        return self.get_object_url(object_name)

    def delete_object(self, object_name: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_name)

    def get_object_url(self, object_name: str) -> str:
        if settings.storage.base_url:
            return urljoin(settings.storage.base_url.rstrip("/") + "/", quote_object_name(object_name))
        return self.get_presigned_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_name},
                ExpiresIn=settings.storage.presign_expire_seconds,
            )
        )


class S3Storage(S3CompatibleStorage):
    pass


class MinioStorage(S3CompatibleStorage):
    def __init__(self) -> None:
        super().__init__(force_path_style=True)
