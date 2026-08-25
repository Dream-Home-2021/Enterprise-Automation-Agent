from .visualization_agent import VisualizationAgent
from .code_agent import CodeAgent
from .search_agent import SearchAgent
from .report_agent import ReportAgent
from .quality_review_agent import QualityReviewAgent
from .refiner_agent import RefinerAgent
from .hypothesis_agent import HypothesisAgent
from .process_agent import ProcessAgent
from .note_agent import NoteAgent
from .chat_agent import ChatAgent
from ..config import WORKING_DIRECTORY

class AgentFactory:
    """Agent  Agent 
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        self.language_model_manager = language_model_manager
        self.team_members = team_members
        self.working_directory = working_directory

    def create_agent(self, agent_name: str):
        """ Agent 
        """
        agent_mapping = {
            "visualization_agent": VisualizationAgent,
            "code_agent": CodeAgent,
            "search_agent": SearchAgent,
            "report_agent": ReportAgent,
            "quality_review_agent": QualityReviewAgent,
            "refiner_agent": RefinerAgent,
            "hypothesis_agent": HypothesisAgent,
            "process_agent": ProcessAgent,
            "note_agent": NoteAgent,
		    "chat_agent": ChatAgent,
        }
        agent_class = agent_mapping.get(agent_name)
        if not agent_class:
            raise ValueError(f"Agent '{agent_name}' not implemented.")
        # 实例化并返回，传入三个公共参数
        return agent_class(
            language_model_manager=self.language_model_manager,
            team_members=self.team_members,
            working_directory=self.working_directory
        )
