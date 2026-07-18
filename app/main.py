import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    app_dir = Path(__file__).resolve().parent
    project_root = app_dir.parent
    sys.path = [path for path in sys.path if Path(path or ".").resolve() != app_dir]
    sys.path.insert(0, str(project_root))

import uvicorn

from app.core.config.settings import settings
from app.factory import create_app

app = create_app()

# 修复 python -m app.main 导致的 __main__/app.main 双重导入问题：
# 当通过 "python -m app.main" 启动时，模块先以 __main__ 执行，
# 然后 uvicorn 又 import "app.main" 导致 create_app() 被执行两次。
# 将当前模块注册为 app.main，让 uvicorn 复用同一个 app 实例。
if __name__ == "__main__":
    sys.modules["app.main"] = sys.modules["__main__"]


def main() -> None:
    workers = _resolve_workers()
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        workers=None if settings.app.debug else workers,
    )


def _resolve_workers() -> int:
    if settings.app.debug:
        return 1
    if settings.app.workers > 0:
        return settings.app.workers
    cpu_count = os.cpu_count() or 1
    return max(1, min(cpu_count, settings.app.worker_max))


if __name__ == "__main__":
    main()
