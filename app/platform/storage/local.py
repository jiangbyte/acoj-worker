from pathlib import Path

from app.core.config.settings import PROJECT_ROOT, settings
from app.platform.storage.url import build_file_access_url


class LocalStorage:
    def __init__(self, root: str = "./storage") -> None:
        root_path = Path(root)
        self.root = root_path if root_path.is_absolute() else PROJECT_ROOT / root_path
        self.root = self.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def upload_bytes(self, object_name: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        _ = content_type
        target = self.get_path(object_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return self.get_object_url(object_name)

    def delete_object(self, object_name: str) -> None:
        target = self.get_path(object_name)
        if target.exists():
            target.unlink()

    def get_object_url(self, object_name: str) -> str:
        return build_file_access_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        return self.get_object_url(object_name)

    def get_path(self, object_name: str) -> Path:
        target = (self.root / object_name).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Invalid object name")
        return target
