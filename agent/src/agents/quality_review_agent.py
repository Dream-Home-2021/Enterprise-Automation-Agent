from typing import Any, Dict, Literal, List, TYPE_CHECKING
from pydantic import BaseModel, Field

from ..tools.basetool import list_directory
from ..tools.file_edit import create_document, read_document, edit_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.node import get_state_attr
from ..logger import setup_logger


logger = setup_logger()

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class QualityOutput(BaseModel):
    """ Pydantic """
    needs_revision: bool = Field(
        description="是否需要修订"
    )
    feedback: str = Field(
        description="需要改进的具体反馈"
    )

class QualityReviewAgent(BaseAgent):
    """ Agent"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """ QualityReviewAgent

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
            response_format=QualityOutput
        )

    def _get_tools(self) -> List:
        """ QualityReviewAgent """

        return [create_document, read_document, edit_document, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """ State 

        Args:
            state: 当前工作流状态。
            output: Agent 的 QualityOutput 或解析失败时的原始字符串。

        Returns:
            包含修订控制字段的字典。
        """

        # 这时用启发式规则做"兜底判断"
        if isinstance(output, str):
            logger.warning(f"QualityReviewAgent received string instead of QualityOutput: {output[:100]}...")

            needs_revision = any(kw in output.lower() for kw in ["revision", "improve", "fix", "correct", "change"])
            feedback = output
        else:

            needs_revision = getattr(output, "needs_revision", False)
            feedback = getattr(output, "feedback", "")

        updates: Dict[str, Any] = {"needs_revision": needs_revision}


        current_count = get_state_attr(state, "revision_count", 0)
        if needs_revision:
            updates["quality_feedback"] = feedback
            updates["revision_count"] = current_count + 1
        else:
            # 审查通过：清除反馈并重置计数器
            updates["quality_feedback"] = None
            updates["revision_count"] = 0

        return updates
