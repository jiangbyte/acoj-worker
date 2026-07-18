"""检查当前数据库结构是否与 SQLAlchemy 模型一致。"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    config = Config(str(project_root / "alembic.ini"))
    command.check(config)


if __name__ == "__main__":
    main()
