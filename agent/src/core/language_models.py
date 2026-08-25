from __future__ import annotations
from typing import Any, TYPE_CHECKING
from ..logger import setup_logger
from ..llm.factory import ProviderFactory
from ..config import AGENT_MODELS

if TYPE_CHECKING:
    from ..llm.providers.base import BaseProvider


class LanguageModelManager:
    """
    """

    def __init__(self) -> None:
        """"""
        self.logger = setup_logger()
        self.provider_factory = ProviderFactory()

    def get_provider(self, agent_name: str) -> BaseProvider:
        """ Agent  LLM Provider 
        """
        provider_name = AGENT_MODELS.get_provider(agent_name)
        if not provider_name:
            raise ValueError(f"No provider configured for agent '{agent_name}'")
        # 用工厂创建对应的供应商实例并返回
        return self.provider_factory.create_provider(provider_name)

    def get_model_config(self, agent_name: str) -> dict[str, Any]:
        """ Agent modeltemperature 
        """
        config = AGENT_MODELS.get_model_config(agent_name)
        if not config:
            raise ValueError(f"No model config configured for agent '{agent_name}'")
        return config

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """ Agent  max_iterations 
        """
        return AGENT_MODELS.get_agent_config(agent_name)
