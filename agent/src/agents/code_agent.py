# ============================================================
# 文件角色: src/agents/code_agent.py — 代码 Agent，负责编写和执行 Python 代码
# 小白导读:
#   - CodeAgent: 一个能写代码、跑代码的 AI 角色，类比"程序员"。
#   - Artifact:  Agent 完成任务后产出的"产物"，如代码、报告、图表。
#   - Pydantic: 一个 Python 库，用于定义数据结构和校验数据格式。
# 协作关系:
#   - 继承 BaseAgent，获得所有基础能力。
#   - 被 AgentFactory 按名字创建。
#   - 产出 code_artifacts 写入全局 State。
# ============================================================

from typing import Any, Dict, List, TYPE_CHECKING  # 类型提示工具

from ..tools.basetool import execute_code, execute_command, list_directory  # 导入基础工具函数
from ..tools.file_edit import read_document  # 导入文件读取工具
from .base import BaseAgent  # 导入父类
from ..config import WORKING_DIRECTORY  # 导入工作目录配置
from ..core.schemas import ArtifactSchema  # 导入产物数据结构定义
from ..core.node import update_artifact_dict, get_state_attr  # 导入状态更新辅助函数

if TYPE_CHECKING:  # 仅类型检查时导入，运行时不会执行
    from ..core.language_models import LanguageModelManager  # 语言模型管理器类型
    from ..core.state import State  # 状态类型

class CodeAgent(BaseAgent):
    """负责编写和执行 Python 代码进行数据处理。
    小白导读: 这个 Agent 会写代码、跑代码，把结果存到共享状态里。
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        # 调用父类构造函数，设置 Agent 名字和输出格式
        super().__init__(
            agent_name="code_agent",  # 本 Agent 的名字
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )
        self.response_format = ArtifactSchema  # 输出格式强制为 ArtifactSchema（Pydantic 模型）

    def _get_tools(self):
        """返回本 Agent 可用的工具列表。
        小白导读: 代码 Agent 能读文件、写代码、执行命令、列目录。
        """
        return [read_document, execute_code, execute_command, list_directory]  # 四个工具

    def get_state_updates(self, state, output):
        """从 Agent 输出中提取代码产物，更新到全局状态。
        小白导读: 把 Agent 跑出来的代码结果存到 state["code_artifacts"] 里。
        假数据示例:
            输入: output = {"artifacts": {"result1": {"type": "code", "content": "print(1)"}}}
            返回: {"code_artifacts": {"result1": {"type": "code", "content": "print(1)"}}}
        """
        # 内部辅助函数：安全地从对象或字典中取值
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):  # 如果是字典
                return obj.get(key, default)  # 用 dict.get
            return getattr(obj, key, default)  # 否则用属性访问

        # 从当前状态中获取已有的代码产物
        current = get_state_attr(state, "code_artifacts", {})
        # 从 Agent 输出中提取新的产物
        new_data = safe_get(output, "artifacts", output)
        # 合并新旧产物并返回
        return {"code_artifacts": update_artifact_dict(current, new_data)}
