from typing import Type
from langchain_google_genai import ChatGoogleGenerativeAI
from .base import BaseProvider

class GoogleProvider(BaseProvider):
    """Google 模型 Provider。"""

    def get_model_class(self) -> Type:
        """返回 ChatGoogleGenerativeAI 类。"""
        return ChatGoogleGenerativeAI
