from typing import Type
from langchain_ollama import ChatOllama

from .base import BaseProvider

class OllamaProvider(BaseProvider):
    """Ollama 本地模型 Provider。"""

    def get_model_class(self) -> Type:
        """返回 ChatOllama 类。"""
        return ChatOllama
