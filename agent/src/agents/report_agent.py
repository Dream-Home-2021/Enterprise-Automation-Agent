# =============================================================================
# 文件角色: ReportAgent —— 研究报告的"主笔 / 撰稿人"
# 小白导读:
#   - Report: 最终的研究报告，是整个工作流的"交付物"
#   - ArtifactSchema: 定义产物结构的 Schema，包含 artifacts 字段（文档集合）
#   - report_artifacts: State 中存储所有报告产物的"文件夹"
# 协作关系:
#   - 接收精炼后的素材（来自 RefinerAgent）
#   - 输出报告产物，由 QualityReviewAgent 审查
#   - 如果审查不通过，被打回重写；通过则进入 VisualizationAgent 生成图表
# =============================================================================

from typing import Any, Dict, List, TYPE_CHECKING

from ..tools.basetool import list_directory
from ..tools.file_edit import create_document, read_document, edit_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.schemas import ArtifactSchema
from ..core.node import update_artifact_dict, get_state_attr

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class ReportAgent(BaseAgent):
    """负责撰写综合研究报告的 Agent。"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 ReportAgent。

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """
        super().__init__(
            agent_name="report_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )
        # 小白导读: 产物格式为 ArtifactSchema，包含 artifacts 字段
        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """获取报告撰写所需的工具列表。"""
        # 小白导读: 报告撰写只需文件操作，不需要联网搜索（素材已由 RefinerAgent 准备好）
        return [create_document, read_document, edit_document, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """返回报告产物的 State 更新。

        Args:
            state: 当前工作流状态。
            output: Agent 的 ArtifactSchema 输出。

        Returns:
            包含 'report_artifacts' 字段更新的字典。
        """
        # 小白导读: 读取已有的报告产物（可能之前已被部分写入）
        current = get_state_attr(state, "report_artifacts", {})
        # 小白导读: 兼容 Pydantic 对象和 dict 两种情况
        new_data = getattr(output, "artifacts", output)
        # 小白导读: update_artifact_dict 把新产物合并到已有产物字典里
        return {"report_artifacts": update_artifact_dict(current, new_data)}
