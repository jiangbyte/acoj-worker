"""运行 Ruff 代码检查。"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    raise SystemExit(subprocess.call([sys.executable, "-m", "ruff", "check", "."]))


if __name__ == "__main__":
    main()
