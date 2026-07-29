"""MinIO 真实联调：上传测例 → download/head → file_cache → Celery 判题（FILE key）。

凭据优先环境变量，否则读 docker `dev-minio`；bucket 默认 acoj-worker-test。
无 mock 假数据。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from app.core.config.enums import StorageProvider
from app.modules.judge import data_loader, file_cache
from app.modules.judge.schemas import JudgeResultOut
from app.modules.judge.tasks import execute_judge
from app.platform.storage.config import StorageConfig
from app.platform.storage.s3 import MinioStorage
from tests.judge_helper import LANG_PYTHON3, build_payload

BUCKET = os.environ.get("ACOJ_MINIO_TEST_BUCKET", "acoj-worker-test")
ENDPOINT = os.environ.get("ACOJ_MINIO_ENDPOINT", "http://127.0.0.1:9000")


def _docker_env(name: str) -> str | None:
    try:
        return subprocess.check_output(
            ["docker", "exec", "dev-minio", "printenv", name],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip() or None
    except Exception:
        return None


def _minio_creds() -> tuple[str, str]:
    access = os.environ.get("ACOJ_MINIO_ACCESS_KEY") or os.environ.get("MINIO_ROOT_USER")
    secret = os.environ.get("ACOJ_MINIO_SECRET_KEY") or os.environ.get("MINIO_ROOT_PASSWORD")
    if not (access and secret):
        access = _docker_env("MINIO_ROOT_USER")
        secret = _docker_env("MINIO_ROOT_PASSWORD")
    if not (access and secret):
        pytest.skip("MinIO credentials unavailable")
    return access, secret


@pytest.fixture(scope="module")
def minio_storage():
    access, secret = _minio_creds()
    cfg = StorageConfig(
        id="minio-test",
        name="minio-test",
        provider=StorageProvider.MINIO,
        bucket=BUCKET,
        endpoint=ENDPOINT,
        access_key=access,
        secret_key=secret,
        region="us-east-1",
        use_ssl=False,
    )
    storage = MinioStorage(cfg)
    try:
        storage.client.head_bucket(Bucket=BUCKET)
    except Exception:
        try:
            storage.client.create_bucket(Bucket=BUCKET)
        except Exception as exc:
            pytest.skip(f"MinIO unreachable: {exc}")
    return storage


@pytest.fixture
def wire_minio(minio_storage, tmp_path, monkeypatch):
    """把判题数据加载 / 缓存接到真实 MinIO（非 mock 数据，只是切换存储后端）。"""
    root = tmp_path / "judge-cache"
    root.mkdir()
    monkeypatch.setattr(file_cache, "CACHE_ROOT", root)
    monkeypatch.setattr(file_cache, "CACHE_ENABLED", True)
    monkeypatch.setattr(file_cache, "CACHE_MAX_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(file_cache, "CACHE_TTL_SECONDS", 86400)
    monkeypatch.setattr(file_cache, "_CACHE_INITIALIZED", True)

    def _get():
        return minio_storage

    monkeypatch.setattr("app.platform.storage.manager.get_storage", _get)
    data_loader._storage = minio_storage
    yield minio_storage
    data_loader._storage = None


def test_minio_upload_download_head(minio_storage):
    key = f"judge-it/{uuid.uuid4().hex}/sample.in"
    content = b"1 2\n3 4\n" + (b"x" * 4096)
    minio_storage.upload_bytes(key, content, content_type="text/plain")
    try:
        assert minio_storage.download_bytes(key) == content
        meta = minio_storage.head_object(key)
        assert meta is not None
        assert meta["content_length"] == len(content)
        assert meta["etag"]
        assert minio_storage.head_object(f"judge-it/missing-{uuid.uuid4().hex}") is None
    finally:
        minio_storage.delete_object(key)


def test_minio_file_cache_download_and_hit(wire_minio, tmp_path):
    storage = wire_minio
    key = f"judge-it/{uuid.uuid4().hex}/cache.out"
    content = ("line\n" * 500 + "TAIL\n").encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()
    storage.upload_bytes(key, content)
    try:
        path1 = file_cache.resolve_or_download(key, sha)
        assert path1 is not None
        assert Path(path1).read_bytes() == content
        storage.delete_object(key)
        path2 = file_cache.resolve_or_download(key, sha)
        assert path2 is not None
        assert Path(path2).read_bytes() == content
    finally:
        try:
            storage.delete_object(key)
        except Exception:
            pass


def test_minio_multiple_testdata_files(wire_minio):
    storage = wire_minio
    prefix = f"judge-it/{uuid.uuid4().hex}"
    files = {
        f"{prefix}/1.in": b"1 2\n",
        f"{prefix}/1.out": b"3\n",
        f"{prefix}/2.in": b"10 20\n",
        f"{prefix}/2.out": b"30\n",
    }
    for name, body in files.items():
        storage.upload_bytes(name, body)
    try:
        for name, body in files.items():
            sha = hashlib.sha256(body).hexdigest()
            local = file_cache.resolve_or_download(name, sha)
            assert local is not None
            assert Path(local).read_bytes() == body
            head = storage.head_object(name)
            assert head is not None
            assert head["content_length"] == len(body)
    finally:
        for name in files:
            try:
                storage.delete_object(name)
            except Exception:
                pass


def test_minio_file_keys_real_judge(wire_minio):
    """上传真实 in/out 到 MinIO，payload 只传 FILE key，进程内 Celery apply 判题。"""
    storage = wire_minio
    prefix = f"judge-it/{uuid.uuid4().hex}"
    inp = b"alpha\n"
    out = b"alpha\n"
    in_key = f"{prefix}/1.in"
    out_key = f"{prefix}/1.out"
    storage.upload_bytes(in_key, inp)
    storage.upload_bytes(out_key, out)
    in_sha = hashlib.sha256(inp).hexdigest()
    out_sha = hashlib.sha256(out).hexdigest()
    sid = f"it-minio-file-{uuid.uuid4().hex[:8]}"
    src = 'import sys\nprint(sys.stdin.read(), end="")\n'
    payload = build_payload(
        sid,
        "STANDARD",
        src,
        LANG_PYTHON3,
        [
            {
                "case_no": 1,
                "points": 100.0,
                "time_limit_ms": 2000,
                "memory_limit_kb": 65536,
                "input_file": in_key,
                "output_file": out_key,
                "input_sha256": in_sha,
                "output_sha256": out_sha,
                "input_inline": "",
                "output_inline": None,
            }
        ],
    )
    try:
        result = execute_judge.apply(args=[payload]).get(timeout=60)
        parsed = JudgeResultOut.model_validate(result)
        assert parsed.status == "COMPLETED"
        assert parsed.result == "AC"
        assert parsed.cases[0].case_no == 1
    finally:
        storage.delete_object(in_key)
        storage.delete_object(out_key)
