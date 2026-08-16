# ============================================================================
# 文件角色：语言模型管理器（LanguageModelManager）
# 小白导读：
#   - LLM（Large Language Model，大语言模型）：像 ChatGPT 这样的"大脑"，负责理解/生成文本。
#   - Provider（供应商）：不同公司提供的 LLM 服务，如 OpenAI、Google、Anthropic 等。
#   - AGENT_MODELS：全局配置字典，记录每个 Agent（工人）该用哪个供应商的模型。
# 协作关系：
#   - 被 src/agents/ 下各 Agent 调用，为它们分配合适的 LLM 供应商。
#   - 依赖 src/llm/ 下的 ProviderFactory 来创建具体的供应商实例。
#   - 依赖 src/config.py 中的 AGENT_MODELS 全局配置。
# ============================================================================

from __future__ import annotations  # 允许在类型注解中使用类名字符串（延迟求值），兼容 Python 3.7+
from typing import Any, TYPE_CHECKING  # Any：任意类型；TYPE_CHECKING：类型检查专用标志
from ..logger import setup_logger  # 导入日志工厂，用于创建带模块名的 logger
from ..llm.factory import ProviderFactory  # 导入供应商工厂类，用于创建 LLM 供应商实例
from ..config import AGENT_MODELS  # 导入全局配置：每个 Agent 对应的模型供应商信息

if TYPE_CHECKING:  # 仅在类型检查（如 IDE、mypy）时执行，运行时不导入，避免循环依赖
    from ..llm.providers.base import BaseProvider  # 导入 LLM 供应商的基类，用于类型注解


class LanguageModelManager:
    """
    语言模型管理器 —— 根据 Agent 名称获取对应的 LLM Provider 和模型配置。
    是 ProviderFactory 和 AGENT_MODELS 单例的统一门面。
    小白导读: 这个类是"调度中心"，根据 Agent 的名字分配对应的 LLM 供应商。
    """

    def __init__(self) -> None:
        """初始化管理器：创建日志对象和供应商工厂实例。"""
        self.logger = setup_logger()  # 创建带模块名的日志对象，方便追踪日志来源
        self.provider_factory = ProviderFactory()  # 实例化工厂类，后续用它创建供应商

    def get_provider(self, agent_name: str) -> BaseProvider:
        """获取指定 Agent 的 LLM Provider 实例。

        小白导读: 先从配置查供应商名字，再用工厂创建实例（工厂模式）。
        """
        # 从全局配置中查出该 Agent 对应的供应商名称（如 "openai"）
        provider_name = AGENT_MODELS.get_provider(agent_name)
        if not provider_name:  # 如果配置里没找到，抛出明确错误
            raise ValueError(f"No provider configured for agent '{agent_name}'")
        # 用工厂创建对应的供应商实例并返回
        return self.provider_factory.create_provider(provider_name)

    def get_model_config(self, agent_name: str) -> dict[str, Any]:
        """获取指定 Agent 的模型配置（model、temperature 等）。

        小白导读: temperature 控制回答的随机性，0 表示确定，1 表示更有创意。
        """
        # 从全局配置中读取该 Agent 的模型参数字典
        config = AGENT_MODELS.get_model_config(agent_name)
        if not config:  # 如果配置缺失，抛出明确错误
            raise ValueError(f"No model config configured for agent '{agent_name}'")
        return config

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """获取指定 Agent 的完整配置（含 max_iterations 等）。

        小白导读: max_iterations 是 Agent 最多循环几步，防止它无限跑下去。
        """
        return AGENT_MODELS.get_agent_config(agent_name)
