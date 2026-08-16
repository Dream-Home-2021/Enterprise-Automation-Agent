from typing import Type
from langchain_anthropic import ChatAnthropic
from .base import BaseProvider

class AnthropicProvider(BaseProvider):
    """Anthropic 模型 Provider。"""

    def get_model_class(self) -> Type:
        """返回 ChatAnthropic 类。"""
        return ChatAnthropic
