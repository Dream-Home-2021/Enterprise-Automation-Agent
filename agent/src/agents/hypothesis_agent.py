from typing import Any, Dict, List, TYPE_CHECKING

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.agent_toolkits.load_tools import load_tools

from .base import BaseAgent
from ..tools.basetool import list_directory
from ..tools.file_edit import collect_data
from ..tools.internet import google_search, scrape_webpages
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class HypothesisAgent(BaseAgent):
    """ Agent
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        super().__init__(
            agent_name="hypothesis_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )

    def _get_tools(self):
        """ Agent 
        """
        api_wrapper = WikipediaAPIWrapper(wiki_client=None)
        # 创建维基百科查询工具
        wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)
        # 组装所有工具
        base_tools = [
            collect_data,
            wikipedia,
            google_search,
            scrape_webpages,
            list_directory
        ] + load_tools(["arxiv"])
        return base_tools

    def get_state_updates(self, state, output):
        """ Agent 
        """
        if isinstance(output, str):
            hypothesis_text = output
        elif hasattr(output, "hypothesis"):
            hypothesis_text = str(output.hypothesis)
        elif hasattr(output, "content"):
            hypothesis_text = str(output.content)
        else:
            hypothesis_text = str(output)
        return {"hypothesis": hypothesis_text}
