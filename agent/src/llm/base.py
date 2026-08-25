from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class BaseProvider(ABC):
    """LLM Provider """

    @abstractmethod
    def get_model_class(self) -> type[Any]:
        """ Provider  ChatOpenAI

        Returns:
            模型类本身（非实例）。
        """
        pass
