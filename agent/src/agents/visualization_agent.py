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

class VisualizationAgent(BaseAgent):
    """ Agent"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """ VisualizationAgent

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """
        super().__init__(
            agent_name="visualization_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )

        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """"""

        return [read_document, execute_code, execute_command, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """ State """

        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)


        current = get_state_attr(state, "data_viz_artifacts", {})
        new_data = safe_get(output, "artifacts", output)

        return {"data_viz_artifacts": update_artifact_dict(current, new_data)}
