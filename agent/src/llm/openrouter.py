from typing import Type, Any

from langchain_openai import ChatOpenAI

from .base import BaseProvider


class OpenRouterProvider(BaseProvider):
    """OpenRouter 模型 Provider。

    OpenRouter 提供 OpenAI 兼容的 /v1 端点，因此直接复用 ChatOpenAI，
    但默认把 openai_api_base 指向 https://openrouter.ai/api/v1。

    用法:
        1. 在 .env 中设置 OPENROUTER_API_KEY=sk-or-v1-...
        2. 在 agent_models.yaml 中把 provider 改为 openrouter
        3. model 字段使用 OpenRouter 的模型 ID，格式为 "厂商/模型名"，
           例如: google/gemini-2.5-pro, openai/gpt-5-mini, anthropic/claude-haiku-4-5
    """

    # OpenRouter 的 OpenAI 兼容端点
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def get_model_class(self) -> Type:
        """返回 ChatOpenAI 类。"""
        return ChatOpenAI

    def get_extra_kwargs(self) -> dict[str, Any]:
        """返回传给 ChatOpenAI 的额外参数（base_url / api_key / headers）。

        小白导读:
            openai_api_base  → 告诉 ChatOpenAI 请求发到 OpenRouter 而不是 OpenAI
            openai_api_key   → OpenRouter 的 API Key（从 .env 读取）
            default_headers  → OpenRouter 推荐的统计头，可选但建议带上
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
