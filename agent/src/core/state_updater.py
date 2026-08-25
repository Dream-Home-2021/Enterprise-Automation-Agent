"""StateUpdater Protocol ——  Agent 
"""

from typing import Protocol, Dict, Any, runtime_checkable

from .state import State


@runtime_checkable
class StateUpdater(Protocol):
    """Agent 
    """

    def get_state_updates(self, state: State, output: Any) -> Dict[str, Any]:
        """ Agent  State 

        Args:
            state: 当前工作流状态。
            output: Agent 的结构化或原始输出。

        Returns:
            字段名 → 新值的映射字典。
        """
        ...
