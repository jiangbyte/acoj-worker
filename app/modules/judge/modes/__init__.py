"""判题模式注册表。新增模式在此注册即可接入编排层。"""

from app.modules.judge.modes.base import BaseJudgeMode
from app.modules.judge.modes.standard import StandardMode
from app.modules.judge.modes.spj import SpecialJudgeMode
from app.modules.judge.modes.interactive import InteractiveMode

MODE_REGISTRY: dict[str, type[BaseJudgeMode]] = {
    "STANDARD": StandardMode,
    "SPECIAL_JUDGE": SpecialJudgeMode,
    "INTERACTIVE": InteractiveMode,
}
