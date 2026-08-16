# ============================================================
# 文件角色: src/agents/note_agent.py — 笔记 Agent，负责记录研究过程
# 小白导读:
#   - NoteAgent: 一个能记录和管理研究过程的 AI 角色，类比"研究助理"。
#   - Pydantic: 一个 Python 库，用于定义数据结构和校验数据格式。
#   - 它用 Pydantic 模型严格定义输出格式，确保每次输出都符合规范。
# 协作关系:
#   - 继承 BaseAgent，获得所有基础能力。
#   - 被 AgentFactory 按名字创建。
#   - 产出多种 artifacts（search/data_viz/code/report）和质量反馈写入全局 State。
# ============================================================

from pydantic import BaseModel, Field  # 导入 Pydantic 数据模型工具
from typing import Sequence, List, TYPE_CHECKING, Any  # 类型提示工具

from langchain_core.messages import BaseMessage  # LangChain 消息基类

from ..tools.file_edit import read_document  # 导入文件读取工具
from ..tools.basetool import list_directory  # 导入目录列表工具
from .base import BaseAgent  # 导入父类
from ..config import WORKING_DIRECTORY  # 导入工作目录配置
from ..core.state import State  # 导入状态类型

if TYPE_CHECKING:  # 仅类型检查时导入
    from ..core.language_models import LanguageModelManager  # 语言模型管理器类型


class NoteOutput(BaseModel):
    """NoteAgent 输出的 Pydantic 模型。
    小白导读: 这个类定义了 NoteAgent 每次输出的数据结构，所有字段都有默认值。
    类比: 像一份表格模板，每次填写都必须符合这个格式。
    """
    messages: List[Any] = Field(default_factory=list, description="新消息")  # 新产生的消息列表
    hypothesis: str = Field(default="", description="更新后的研究假设")  # 当前研究假设
    current_instruction: str = Field(default="", description="更新后的当前指令")  # 当前工作指令
    next_workflow_step: str = Field(default="", description="下一步工作流步骤")  # 下一步做什么
    search_artifacts: str = Field(default="", description="搜索产物")  # 搜索阶段产出
    data_viz_artifacts: str = Field(default="", description="可视化产物")  # 可视化阶段产出
    code_artifacts: str = Field(default="", description="代码产物")  # 代码阶段产出
    report_artifacts: str = Field(default="", description="报告产物")  # 报告阶段产出
    quality_feedback: str = Field(default="", description="质量反馈")  # 质量审查反馈
    needs_revision: bool = Field(default=False, description="是否需要修订")  # 是否需要返工

class NoteAgent(BaseAgent):
    """负责记录研究过程的 Agent（上下文管理器）。
    小白导读: 这个 Agent 像"研究日志员"，记录每一步做了什么、结果如何。
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        # 调用父类构造函数，指定输出格式为 NoteOutput
        super().__init__(
            agent_name="note_agent",  # 本 Agent 的名字
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=NoteOutput  # 强制输出为 NoteOutput 格式
        )

    def _get_tools(self):
        """返回本 Agent 可用的工具列表。
        小白导读: 笔记 Agent 只能读文件和列目录，不能执行代码或搜索。
        """
        return [read_document, list_directory]  # 只给两个只读工具
