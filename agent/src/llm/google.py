from typing import Type
from langchain_google_genai import ChatGoogleGenerativeAI
from .base import BaseProvider

class GoogleProvider(BaseProvider):
    """Google  Provider"""

    def get_model_class(self) -> Type:
        """ ChatGoogleGenerativeAI """
        return ChatGoogleGenerativeAI
