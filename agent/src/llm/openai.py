from typing import Type

from langchain_openai import ChatOpenAI

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI 模型 Provider。"""

    def get_model_class(self) -> Type:
        """返回 ChatOpenAI 类。"""
        return ChatOpenAI
