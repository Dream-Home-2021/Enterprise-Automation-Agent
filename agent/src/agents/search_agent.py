# =============================================================================
# 文件角色: SearchAgent —— 数据采集的"调研员 / 情报员"
# 小白导读:
#   - Search Agent: 负责上网搜资料、读文件、抓网页，是工作流的"先锋"
#   - collect_data: 通用数据采集工具，可以从 CSV/JSON/Excel 等读取结构化数据
#   - arxiv: 学术论文预印本平台（类似"科学家的 arXiv"），搜索学术论文
#   - WikipediaQueryRun: LangChain 封装的 Wikipedia 搜索工具
# 协作关系:
#   - 通常是工作流的第一个 Agent（先锋）
#   - 输出 ArtifactSchema 格式的产物，供 RefinerAgent 精炼
#   - 与 RefinerAgent 工具集相同，但分工不同：Search 侧重"收集"，Refiner 侧重"整理"
# =============================================================================

from typing import Any, Dict, List, TYPE_CHECKING

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.agent_toolkits.load_tools import load_tools

from .base import BaseAgent
from ..tools.basetool import list_directory
from ..tools.file_edit import create_document, read_document, collect_data
from ..tools.internet import google_search, scrape_webpages
from ..config import WORKING_DIRECTORY
from ..core.schemas import ArtifactSchema
from ..core.node import update_artifact_dict, get_state_attr

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager
    from ..core.state import State

class SearchAgent(BaseAgent):
    """负责收集和研究信息的 Agent。"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 SearchAgent。"""
        super().__init__(
            agent_name="search_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
            response_format=ArtifactSchema  # 小白导读: 在构造函数里直接指定 response_format
        )

    def _get_tools(self) -> List:
        """获取信息检索和总结所需的工具列表。"""
        # 小白导读: WikipediaAPIWrapper 是 LangChain 的 Wikipedia 客户端封装
        api_wrapper = WikipediaAPIWrapper(wiki_client=None)
        wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)
        # 小白导读: 组装工具清单 —— 文件读写 + 数据采集 + 互联网搜索 + 学术论文
        base_tools = [
            create_document,       # 创建文件
            read_document,         # 读取文件
            collect_data,          # 小白导读: 通用数据采集（CSV/JSON/Excel 等）
            wikipedia,             # Wikipedia 搜索
            google_search,          # Google 搜索
            scrape_webpages,       # 抓取网页内容
            list_directory         # 列出目录内容
        ] + load_tools(["arxiv"])  # 加载 arxiv 学术论文搜索工具

        return base_tools

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """返回搜索产物的 State 更新。"""
        # 小白导读: safe_get 安全取值，兼容 dict 和 Pydantic 对象
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # 小白导读: 读取已有的搜索产物，与新产物合并
        current = get_state_attr(state, "search_artifacts", {})
        new_data = safe_get(output, "artifacts", output)
        # 小白导读: update_artifact_dict 把新数据合并到已有产物字典
        return {"search_artifacts": update_artifact_dict(current, new_data)}
