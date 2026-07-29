"""Judge Pipeline 集成单元测试 — 已弃用 mock SandboxClient。

真实链路见：
  - tests/integration/test_celery_judge_protocol.py
  - tests/integration/test_minio_download_cache.py
"""

import pytest

pytest.skip(
    "mock SandboxClient 已弃用；请跑 tests/integration/ 真实 Celery + MinIO 测试",
    allow_module_level=True,
)
