# =============================================================================
# 文件角色: ProcessAgent —— 整个数据分析工作流的"项目经理" / 调度中枢
# 小白导读:
#   - Agent: 一个能自主决策、调用工具的 AI 工作单元，类比"专项助理"
#   - LLM (Large Language Model): 大语言模型，Agent 的"大脑"
#   - Schema / Pydantic: 定义输出格式的"合同"，强制 LLM 返回结构化数据
#   - State: 整个工作流的"共享记忆"，所有 Agent 通过它传递信息
#   - workflow_step: 工作流中的"阶段"，如 Search → Coder → Report → FINISH
# 协作关系:
#   - 被 workflow.py 编排，根据 ProcessAgent 的决策路由到下一个 Agent
#   - 输出 ProcessRouteSchema，由 router.py 解析后切换状态
#   - 不调用任何工具，只做"决策"，是最轻量的 Agent
# =============================================================================

from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, List, TYPE_CHECKING

from ..core.language_models import LanguageModelManager
from .base import BaseAgent
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:
    # 小白导读: TYPE_CHECKING 块里的导入只给类型检查器用，运行时不执行，避免循环导入
    from ..core.state import State

class ProcessRouteSchema(BaseModel):
    """选择下一个角色并分配任务的 Schema。

    Attributes:
        next_workflow_step: 下一个要行动的角色（Visualization/Search/Coder/Report/FINISH）。
        current_instruction: 所选 Agent 要执行的详细任务描述。
        todo_list: 当前项目的待完成任务列表。
    """
    # 小白导读: Literal 限定只能从这几个字符串中选一个，防止 LLM 乱写
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
    # 假数据示例:
    # {
    #     "next_workflow_step": "Search",
    #     "current_instruction": "请调研 2024 年 AI 领域融资情况",
    #     "todo_list": ["收集融资数据", "撰写分析报告", "生成可视化图表"]
    # }

class ProcessAgent(BaseAgent):
    """负责监督和协调整个数据分析项目的 Agent（项目经理角色）。"""

    def __init__(self, language_model_manager: LanguageModelManager, team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 ProcessAgent。

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """
        # 小白导读: super().__init__() 调用父类 BaseAgent 的构造函数，复用通用初始化逻辑
        super().__init__(
            agent_name="process_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=ProcessRouteSchema  # 强制 LLM 按 ProcessRouteSchema 格式输出
        )

    def _get_tools(self) -> List:
        """ProcessAgent 不需要工具。"""
        # 小白导读: ProcessAgent 只做决策，不读写文件、不上网，所以返回空列表
        return []

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """返回流程路由决策的 State 更新。

        Args:
            state: 当前工作流状态。
            output: Agent 的 ProcessRouteSchema 输出或 dict。

        Returns:
            包含工作流路由字段的字典。
        """
        # 小白导读: safe_get 是一个"安全取值"的小工具函数
        # 因为 output 可能是 Pydantic 对象也可能是 dict，两种取法都试试
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # 小白导读: 返回的字典会被合并到全局 State 里，驱动下一步工作流
        return {
            "current_instruction": safe_get(output, "current_instruction", safe_get(output, "task", "")),
            "next_workflow_step": safe_get(output, "next_workflow_step", safe_get(output, "next", "")),
            "todo_list": safe_get(output, "todo_list", [])
        }
