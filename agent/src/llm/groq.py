from typing import Type

from langchain_groq import ChatGroq

from .base import BaseProvider


class ChatGroqProvider(BaseProvider):
    """Groq  Provider"""

    def get_model_class(self) -> Type:
        """ ChatGroq """
        return ChatGroq
