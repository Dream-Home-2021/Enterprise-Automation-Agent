from typing import Type, Any

from langchain_openai import ChatOpenAI

from .base import BaseProvider


class OpenRouterProvider(BaseProvider):
    """OpenRouter  Provider
    """

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def get_model_class(self) -> Type:
        """ ChatOpenAI """
        return ChatOpenAI

    def get_extra_kwargs(self) -> dict[str, Any]:
        """ ChatOpenAI base_url / api_key / headers
        """
        import os
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        referer = os.getenv("OPENROUTER_HTTP_REFERER", "")
        title = os.getenv("OPENROUTER_X_TITLE", "")

        headers = {}
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        kwargs: dict[str, Any] = {
            "openai_api_base": self.DEFAULT_BASE_URL,
            "openai_api_key": api_key,
        }
        if headers:
            kwargs["default_headers"] = headers
        return kwargs
