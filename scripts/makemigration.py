"""根据 SQLAlchemy 模型变更自动生成 Alembic 迁移文件。"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    message = "schema change"
    if len(sys.argv) >= 2:
        message = " ".join(sys.argv[1:])

    config = Config(str(project_root / "alembic.ini"))
    command.revision(config, message=message, autogenerate=True)


if __name__ == "__main__":
    main()
