from typing import Type

from langchain_openai import AzureChatOpenAI

from .base import BaseProvider


class AzureChatOpenAIProvider(BaseProvider):
    """Azure OpenAI  Provider"""

    def get_model_class(self) -> Type:
        """ AzureChatOpenAI """
        return AzureChatOpenAI
