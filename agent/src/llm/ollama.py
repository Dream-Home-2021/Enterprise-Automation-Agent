from typing import Type
from langchain_ollama import ChatOllama

from .base import BaseProvider

class OllamaProvider(BaseProvider):
    """Ollama  Provider"""

    def get_model_class(self) -> Type:
        """ ChatOllama """
        return ChatOllama
