from pydantic import BaseModel, Field
from typing import Sequence, List, TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage

from ..tools.file_edit import read_document
from ..tools.basetool import list_directory
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.state import State

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager


class NoteOutput(BaseModel):
    """NoteAgent  Pydantic 
    """
    messages: List[Any] = Field(default_factory=list, description="新消息")
    hypothesis: str = Field(default="", description="更新后的研究假设")
    current_instruction: str = Field(default="", description="更新后的当前指令")
    next_workflow_step: str = Field(default="", description="下一步工作流步骤")
    search_artifacts: str = Field(default="", description="搜索产物")
    data_viz_artifacts: str = Field(default="", description="可视化产物")
    code_artifacts: str = Field(default="", description="代码产物")
    report_artifacts: str = Field(default="", description="报告产物")
    quality_feedback: str = Field(default="", description="质量反馈")
    needs_revision: bool = Field(default=False, description="是否需要修订")

class NoteAgent(BaseAgent):
    """ Agent
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        super().__init__(
            agent_name="note_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=NoteOutput
        )

    def _get_tools(self):
        """ Agent 
        """
        return [read_document, list_directory]
