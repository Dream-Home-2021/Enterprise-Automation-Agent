from typing import Type
from langchain_anthropic import ChatAnthropic
from .base import BaseProvider

class AnthropicProvider(BaseProvider):
    """Anthropic  Provider"""

    def get_model_class(self) -> Type:
        """ ChatAnthropic """
        return ChatAnthropic
