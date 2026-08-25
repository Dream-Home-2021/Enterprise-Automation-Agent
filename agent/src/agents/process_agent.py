from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, List, TYPE_CHECKING

from ..core.language_models import LanguageModelManager
from .base import BaseAgent
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:

    from ..core.state import State

class ProcessRouteSchema(BaseModel):
    """ Schema

    Attributes:
    """

    next_workflow_step: Literal["FINISH", "Visualization", "Search", "Coder", "Report"] = Field(
        description="下一个要行动的角色"
    )
    current_instruction: str = Field(
        description="下一个 Agent 的详细指令"
    )
    todo_list: List[str] = Field(
        default_factory=list,
        description="项目当前的待完成任务列表"
    )
    # {
    #     "next_workflow_step": "Search",
    #     "current_instruction": "请调研 2024 年 AI 领域融资情况",
    #     "todo_list": ["收集融资数据", "撰写分析报告", "生成可视化图表"]
    # }

class ProcessAgent(BaseAgent):
    """ Agent"""

    def __init__(self, language_model_manager: LanguageModelManager, team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """ ProcessAgent

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """

        super().__init__(
            agent_name="process_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=ProcessRouteSchema
        )

    def _get_tools(self) -> List:
        """ProcessAgent """

        return []

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """ State 

        Args:
            state: 当前工作流状态。
            output: Agent 的 ProcessRouteSchema 输出或 dict。

        Returns:
            包含工作流路由字段的字典。
        """

        # 因为 output 可能是 Pydantic 对象也可能是 dict，两种取法都试试
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)


        return {
            "current_instruction": safe_get(output, "current_instruction", safe_get(output, "task", "")),
            "next_workflow_step": safe_get(output, "next_workflow_step", safe_get(output, "next", "")),
            "todo_list": safe_get(output, "todo_list", [])
        }
