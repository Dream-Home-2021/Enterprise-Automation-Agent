from typing import Any, Dict, List, TYPE_CHECKING

from ..tools.basetool import execute_code, execute_command, list_directory
from ..tools.file_edit import read_document
from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..core.schemas import ArtifactSchema
from ..core.node import update_artifact_dict, get_state_attr

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class CodeAgent(BaseAgent):
    """ Python 
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        super().__init__(
            agent_name="code_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )
        self.response_format = ArtifactSchema

    def _get_tools(self):
        """ Agent 
        """
        return [read_document, execute_code, execute_command, list_directory]

    def get_state_updates(self, state, output):
        """ Agent 
        """
        # 内部辅助函数：安全地从对象或字典中取值
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        current = get_state_attr(state, "code_artifacts", {})
        # 从 Agent 输出中提取新的产物
        new_data = safe_get(output, "artifacts", output)
        return {"code_artifacts": update_artifact_dict(current, new_data)}
