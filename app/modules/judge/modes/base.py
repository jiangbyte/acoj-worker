"""判题模式策略基类。所有判题模式实现此接口。"""

from abc import ABC, abstractmethod


class BaseJudgeMode(ABC):
    """判题模式策略基类，同步接口。"""

    @abstractmethod
    def judge(self, payload: dict) -> dict:
        """执行判题，返回 result dict。"""
