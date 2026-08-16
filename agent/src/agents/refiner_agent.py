# =============================================================================
# 文件角色: RefinerAgent —— 研究报告的"润色 / 精炼师"
# 小白导读:
#   - Refine: 精炼、润色，把粗糙的素材整理成高质量报告
#   - WikipediaQueryRun: LangChain 封装的 Wikipedia 搜索工具
#   - arxiv: 学术论文预印本平台，load_tools(["arxiv"]) 加载搜索学术论文的能力
#   - scrape_webpages: 抓取网页内容，把 HTML 转成可读文本
# 协作关系:
#   - 接收原始素材（来自 SearchAgent / CoderAgent）
#   - 输出 ArtifactSchema 格式的产物，供 ReportAgent 或 QualityReviewAgent 使用
#   - 工具集最全：文件读写 + 网页搜索 + Wikipedia + arxiv 论文
# =============================================================================

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
    """负责优化和增强研究报告的 Agent。

    RefinerAgent 汇总所有产物，进行深度整理和精炼。
    """

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 RefinerAgent。

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
        # 小白导读: response_format 在父类基础上覆盖为 ArtifactSchema
        # 因为 RefinerAgent 的产物是"精炼后的文档集合"
        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """获取报告精炼所需的工具列表。"""
        # 小白导读: WikipediaAPIWrapper 是 LangChain 的 Wikipedia 客户端封装
        # wiki_client=None 表示使用默认的 requests 客户端
        api_wrapper = WikipediaAPIWrapper(wiki_client=None)
        wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)
        # 小白导读: 组装工具清单 —— 文件操作 + 互联网搜索 + 学术论文
        base_tools = [
            create_document,       # 创建文件
            read_document,         # 读取文件
            edit_document,         # 编辑文件
            wikipedia,             # 小白导读: Wikipedia 搜索，查百科知识
            google_search,          # 小白导读: Google 搜索，查互联网信息
            scrape_webpages,       # 小白导读: 抓取网页，把网页转成文本
            list_directory         # 小白导读: 列出目录内容，看工作区有哪些文件
        ] + load_tools(["arxiv"])  # 小白导读: 加载 arxiv 学术论文搜索工具

        return base_tools
