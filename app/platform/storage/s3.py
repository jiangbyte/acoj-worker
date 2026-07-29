from typing import Any
from urllib.parse import urljoin

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.platform.storage.config import StorageConfig
from app.platform.storage.url import quote_object_name


class S3CompatibleStorage:
    def __init__(self, config: StorageConfig, *, force_path_style: bool = False) -> None:
        self.config = config
        self.bucket = config.bucket
        endpoint = config.endpoint.rstrip("/")
        scheme = "https" if config.use_ssl else "http"
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            endpoint_url = endpoint
        else:
            endpoint_url = f"{scheme}://{endpoint}"
        config_kwargs = {"signature_version": "s3v4"}
        if force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}
        client_config = Config(**config_kwargs)
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
            config=client_config,
        )

    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_name,
            Body=content,
            ContentType=content_type,
        )
        return self.get_object_url(object_name)

    def download_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=object_name)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def head_object(self, object_name: str) -> dict[str, Any] | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=object_name)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        etag = str(response.get("ETag") or "").strip('"')
        return {
            "etag": etag,
            "content_length": int(response.get("ContentLength") or 0),
        }

    def delete_object(self, object_name: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_name)

    def get_object_url(self, object_name: str) -> str:
        if self.config.base_url:
            return urljoin(self.config.base_url.rstrip("/") + "/", quote_object_name(object_name))
        return self.get_presigned_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_name},
                ExpiresIn=self.config.presign_expire_seconds,
            )
        )


class S3Storage(S3CompatibleStorage):
    pass


class MinioStorage(S3CompatibleStorage):
    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config, force_path_style=True)
