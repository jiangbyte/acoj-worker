"""本地存储 download/head 真实文件测试（无 mock）。远程覆盖见 MinIO 集成测。"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.platform.storage.local import LocalStorage


def test_local_download_and_head():
    root = tempfile.mkdtemp(prefix="acoj-local-storage-")
    storage = LocalStorage(root=root)
    storage.upload_bytes("dir/a.txt", b"hello")
    assert storage.download_bytes("dir/a.txt") == b"hello"
    meta = storage.head_object("dir/a.txt")
    assert meta is not None
    assert meta["content_length"] == 5
    assert meta["etag"]
    assert storage.head_object("missing.txt") is None
    assert Path(root, "dir/a.txt").read_bytes() == b"hello"
