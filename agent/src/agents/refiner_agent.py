from typing import List, TYPE_CHECKING

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.agent_toolkits.load_tools import load_tools

from .base import BaseAgent
from  ..tools.basetool import list_directory
from ..tools.internet import google_search, scrape_webpages
from ..tools.file_edit import create_document, read_document, edit_document
from ..config import WORKING_DIRECTORY
from ..core.schemas import ArtifactSchema

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager

class RefinerAgent(BaseAgent):
    """ Agent
    """

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """ RefinerAgent

        Args:
            language_model_manager: 语言模型配置管理器。
            team_members: 团队成员角色列表。
            working_directory: Agent 数据存储目录。
        """
        super().__init__(
            agent_name="refiner_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )

        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """"""

        # wiki_client=None 表示使用默认的 requests 客户端
        api_wrapper = WikipediaAPIWrapper(wiki_client=None)
        wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)

        base_tools = [
            create_document,
            read_document,
            edit_document,
            wikipedia,
            google_search,
            scrape_webpages,
            list_directory
        ] + load_tools(["arxiv"])

        return base_tools
