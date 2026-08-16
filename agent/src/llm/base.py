from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class BaseProvider(ABC):
    """LLM Provider 抽象基类。"""

    @abstractmethod
    def get_model_class(self) -> type[Any]:
        """获取该 Provider 对应的模型类（如 ChatOpenAI）。

        Returns:
            模型类本身（非实例）。
        """
        pass
