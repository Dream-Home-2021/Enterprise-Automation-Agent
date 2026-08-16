"""StateUpdater Protocol —— 解耦 Agent 具体状态更新逻辑。

该模块定义了 Agent 可实现的中心协议，让每个 Agent 自主声明
"我的输出应如何映射到 State 字段"，从而避免在 agent_node 中
写大量 if-elif 分支。
"""

from typing import Protocol, Dict, Any, runtime_checkable

from .state import State


@runtime_checkable
class StateUpdater(Protocol):
    """Agent 状态更新协议。

    实现此协议的 Agent 可以控制其输出如何映射到 State 字段更新。
    """

    def get_state_updates(self, state: State, output: Any) -> Dict[str, Any]:
        """根据 Agent 输出返回 State 字段更新字典。

        Args:
            state: 当前工作流状态。
            output: Agent 的结构化或原始输出。

        Returns:
            字段名 → 新值的映射字典。
        """
        ...
