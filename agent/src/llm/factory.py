from __future__ import annotations
from typing import Any, TYPE_CHECKING
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider
from .ollama import OllamaProvider
from .azure import AzureChatOpenAIProvider
from .groq import ChatGroqProvider
from .openrouter import OpenRouterProvider

if TYPE_CHECKING:
    from .base import BaseProvider

class ProviderFactory:
    """LLM Provider  Provider """

    def create_provider(self, provider_name: str, **kwargs: Any) -> BaseProvider:
        """ Provider 

        Args:
            provider_name: 供应商名称（openai/anthropic/google/ollama/azure/groq）。
            **kwargs: 传递给 Provider 的额外参数。

        Returns:
            请求的 Provider 实例。

        Raises:
            NotImplementedError: 供应商未实现时抛出。
        """
        if provider_name == "openai":
            return OpenAIProvider()
        elif provider_name == "anthropic":
            return AnthropicProvider()
        elif provider_name == "google":
            return GoogleProvider()
        elif provider_name == "ollama":
            return OllamaProvider()
        elif provider_name == "azure":
            return AzureChatOpenAIProvider()
        elif provider_name == "groq":
            return ChatGroqProvider()
        elif provider_name == "openrouter":
            return OpenRouterProvider()
        else:
            raise NotImplementedError(f"Provider creation for '{provider_name}' is not implemented.")
