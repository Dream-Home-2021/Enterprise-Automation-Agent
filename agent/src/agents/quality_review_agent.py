# =============================================================================
# 文件角色: QualityReviewAgent —— 研究报告的"质检员"
# 小白导读:
#   - Quality Review: 质量审查，LLM 扮演"审稿人"角色，判断报告是否达标
#   - needs_revision: 布尔标志，True=打回修改，False=审查通过
#   - revision_count: 记录被打回几次，防止无限循环
#   - heuristic: 启发式规则，用关键词匹配做"兜底判断"
# 协作关系:
#   - 接收上一步 Agent（如 ReportAgent）的产物
#   - 输出 QualityOutput，由 workflow 决定是否回退到 RefinerAgent 重做
#   - 与 ProcessAgent 配合：如果 revision_count 过高，ProcessAgent 可强制结束
# =============================================================================

from typing import Any, Dict, Literal, List, TYPE_CHECKING
from pydantic import BaseModel, Field

from ..tools.basetool import list_directory
from ..tools.file_edit import create_document, read_document, edit_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.node import get_state_attr
from ..logger import setup_logger

# 小白导读: 初始化日志模块，方便调试和追踪 Agent 行为
logger = setup_logger()

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class QualityOutput(BaseModel):
    """质量审查输出的 Pydantic 模型。"""
    needs_revision: bool = Field(
        description="是否需要修订"
    )
    feedback: str = Field(
        description="需要改进的具体反馈"
    )
    # 假数据示例（需要修订）:
    # {"needs_revision": true, "feedback": "数据来源不可靠，请补充 2024 年最新数据"}
    # 假数据示例（通过）:
    # {"needs_revision": false, "feedback": ""}

class QualityReviewAgent(BaseAgent):
    """负责审查研究输出质量的 Agent。"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 QualityReviewAgent。

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """
        super().__init__(
            agent_name="quality_review_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=QualityOutput  # 强制 LLM 按 QualityOutput 格式输出
        )

    def _get_tools(self) -> List:
        """获取 QualityReviewAgent 的工具列表。"""
        # 小白导读: 质检员需要读写文件来查看和批注报告
        return [create_document, read_document, edit_document, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """返回质量审查决策的 State 更新。

        管理 revision_count 和 quality_feedback 生命周期：
        - needs_revision=True：保存反馈并递增 revision_count
        - needs_revision=False：清除反馈并重置 revision_count

        Args:
            state: 当前工作流状态。
            output: Agent 的 QualityOutput 或解析失败时的原始字符串。

        Returns:
            包含修订控制字段的字典。
        """
        # 小白导读: 防御性编程 —— LLM 有时不按 Schema 输出，会返回纯字符串
        # 这时用启发式规则做"兜底判断"
        if isinstance(output, str):
            logger.warning(f"QualityReviewAgent received string instead of QualityOutput: {output[:100]}...")
            # 小白导读: 关键词匹配 —— 如果反馈里出现这些词，推测需要修订
            needs_revision = any(kw in output.lower() for kw in ["revision", "improve", "fix", "correct", "change"])
            feedback = output
        else:
            # 小白导读: 正常路径 —— LLM 乖乖返回了结构化数据
            needs_revision = getattr(output, "needs_revision", False)
            feedback = getattr(output, "feedback", "")

        updates: Dict[str, Any] = {"needs_revision": needs_revision}

        # 小白导读: 从 State 里读取当前已被打回过几次
        current_count = get_state_attr(state, "revision_count", 0)
        if needs_revision:
            # 打回：保存反馈内容，计数器 +1
            updates["quality_feedback"] = feedback
            updates["revision_count"] = current_count + 1
        else:
            # 审查通过：清除反馈并重置计数器
            updates["quality_feedback"] = None
            updates["revision_count"] = 0

        return updates
