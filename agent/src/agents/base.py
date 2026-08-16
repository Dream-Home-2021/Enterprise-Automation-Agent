from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from ..logger import setup_logger
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.agent_config_loader import AgentConfigLoader

logger = setup_logger()


class BaseAgent(ABC):

    SYSTEM_PROMPT_PREFIX = "SYSTEM_PROMPT:"

    _config_loader: AgentConfigLoader | None = None

    @classmethod
    def get_config_loader(cls) -> AgentConfigLoader:
        if cls._config_loader is None:
            from ..core.agent_config_loader import AgentConfigLoader
            cls._config_loader = AgentConfigLoader()
        return cls._config_loader

    def __init__(
        self,
        agent_name: str,
        language_model_manager: LanguageModelManager,
        team_members: list[str],
        working_directory: str = WORKING_DIRECTORY,
        response_format: Any = None,
    ) -> None:
        self.agent_name = agent_name
        self.language_model_manager = language_model_manager
        self.team_members = team_members
        self.working_directory = working_directory
        self.response_format = response_format

        self.model = self._create_model()
        role_prompt = self._load_system_prompt()
        tools = self._load_all_tools()

        agent_config = self.language_model_manager.get_agent_config(self.agent_name)
        self.max_iterations = agent_config.get('max_iterations', 15)

        self.agent = self._create_base_agent(
            self.model,
            tools,
            role_prompt,
            team_members,
            response_format,
            max_iterations=self.max_iterations,
        )

    def _load_all_tools(self) -> list[Any]:
        tools: list[Any] = []
        config_tools = self._load_tools_from_config()
        if config_tools:
            tools.extend(config_tools)
        else:
            hardcoded_tools = self._get_tools()
            if hardcoded_tools:
                tools.extend(hardcoded_tools)
        try:
            loader = self.get_config_loader()
            metadata = loader.load_metadata(self.agent_name)
            if metadata.skills:
                from ..tools.skills import LookupSkill
                tools.append(LookupSkill())
        except Exception as e:
            logger.warning(f"Failed to check skills: {e}")
        mcp_tools = self._load_mcp_tools()
        if mcp_tools:
            tools.extend(mcp_tools)
        return tools

    def _load_tools_from_config(self) -> list[Any]:
        try:
            loader = self.get_config_loader()
            metadata = loader.load_metadata(self.agent_name)
            if not metadata.tools:
                return []
            from ..tools.factory import ToolFactory
            return ToolFactory.get_tools(metadata.tools)
        except Exception as e:
            return []

    def _load_mcp_tools(self) -> list[Any]:
        try:
            loader = self.get_config_loader()
            mcp_config = loader.load_mcp_config(self.agent_name)
            server_names = list(mcp_config.get("servers", {}).keys())
            if not server_names:
                return []
            from ..tools.factory import ToolFactory
            return ToolFactory.get_mcp_tools(server_names)
        except Exception as e:
            return []

    def _create_base_agent(self, model, tools, role_prompt, team_members, response_format=None, max_iterations=15):
        tool_names = ", ".join([tool.name for tool in tools])
        team_members_str = ", ".join(team_members)
        if role_prompt.startswith(self.SYSTEM_PROMPT_PREFIX):
            system_prompt = role_prompt[len(self.SYSTEM_PROMPT_PREFIX):]
        else:
            system_prompt = (
                f"You have access to the following tools: {tool_names}. "
                f"Your specific role: {role_prompt}\n"
                f"Work autonomously. "
                f"You are {self.agent_name} of team: {team_members_str}.\n"
            )
        agent = create_agent(model=model, tools=tools, system_prompt=system_prompt, response_format=response_format)
        if hasattr(agent, "max_iterations"):
            agent.max_iterations = max_iterations
        return agent

    def _create_model(self) -> ChatOpenAI:
        provider = self.language_model_manager.get_provider(self.agent_name)
        model_class = provider.get_model_class()
        config = self.language_model_manager.get_model_config(self.agent_name).copy()
        if "timeout" not in config:
            config["timeout"] = 60
        if hasattr(provider, "get_extra_kwargs"):
            config.update(provider.get_extra_kwargs())
        return model_class(**config)

    def invoke(self, state: Any) -> Any:
        config = {"recursion_limit": self.max_iterations}
        return self.agent.invoke(state, config=config)

    def _load_system_prompt(self) -> str:
        try:
            loader = self.get_config_loader()
            return loader.load_system_prompt(self.agent_name)
        except FileNotFoundError:
            return self._get_system_prompt()
        except Exception:
            return self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        return ""

    @abstractmethod
    def _get_tools(self) -> list[Any]:
        pass

    def get_state_updates(self, state, output) -> dict[str, Any]:
        return {}
