from typing import Type

from langchain_openai import ChatOpenAI

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI  Provider"""

    def get_model_class(self) -> Type:
        """ ChatOpenAI """
        return ChatOpenAI
