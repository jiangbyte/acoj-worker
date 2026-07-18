"""启动后端开发服务入口。"""

import os
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    from app.main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
