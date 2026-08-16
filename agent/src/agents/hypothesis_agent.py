# ============================================================
# 文件角色: src/agents/hypothesis_agent.py — 假设生成 Agent
# 小白导读:
#   - HypothesisAgent: 一个能提出研究假设的 AI 角色，类比"科学家"。
#   - 它可以使用维基百科、Google 搜索、arXiv 论文等工具收集信息。
#   - arXiv: 一个免费的学术论文预印本平台，类比"科学论文图书馆"。
# 协作关系:
#   - 继承 BaseAgent，获得所有基础能力。
#   - 被 AgentFactory 按名字创建。
#   - 产出 hypothesis 写入全局 State。
# ============================================================

from typing import Any, Dict, List, TYPE_CHECKING  # 类型提示工具

from langchain_community.tools import WikipediaQueryRun  # LangChain 维基百科工具封装
from langchain_community.utilities import WikipediaAPIWrapper  # 维基百科 API 包装器
from langchain_community.agent_toolkits.load_tools import load_tools  # LangChain 工具加载函数

from .base import BaseAgent  # 导入父类
from ..tools.basetool import list_directory  # 导入目录列表工具
from ..tools.file_edit import collect_data  # 导入数据收集工具
from ..tools.internet import google_search, scrape_webpages  # 导入 Google 搜索和网页抓取工具
from ..config import WORKING_DIRECTORY  # 导入工作目录配置

if TYPE_CHECKING:  # 仅类型检查时导入
    from ..core.language_models import LanguageModelManager  # 语言模型管理器类型
    from ..core.state import State  # 状态类型

class HypothesisAgent(BaseAgent):
    """负责生成研究假设的 Agent。
    小白导读: 这个 Agent 会搜索维基百科、Google、arXiv 来形成研究假设。
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        # 调用父类构造函数
        super().__init__(
            agent_name="hypothesis_agent",  # 本 Agent 的名字
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory
        )

    def _get_tools(self):
        """返回本 Agent 可用的工具列表。
        小白导读: 包括维基百科查询、Google 搜索、网页抓取、arXiv 论文搜索等。
        """
        # 创建维基百科 API 包装器
        api_wrapper = WikipediaAPIWrapper(wiki_client=None)
        # 创建维基百科查询工具
        wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)
        # 组装所有工具
        base_tools = [
            collect_data,  # 数据收集工具
            wikipedia,  # 维基百科查询
            google_search,  # Google 搜索
            scrape_webpages,  # 网页内容抓取
            list_directory  # 目录列表
        ] + load_tools(["arxiv"])  # 加载 arXiv 论文搜索工具
        return base_tools  # 返回完整工具列表

    def get_state_updates(self, state, output):
        """从 Agent 输出中提取研究假设文本，更新到全局状态。
        小白导读: 兼容多种输出格式（字符串、对象、字典），统一提取假设文本。
        假数据示例:
            输入: output = "我认为 X 和 Y 相关"
            返回: {"hypothesis": "我认为 X 和 Y 相关"}
        """
        if isinstance(output, str):  # 如果输出是纯字符串
            hypothesis_text = output  # 直接使用
        elif hasattr(output, "hypothesis"):  # 如果有 hypothesis 属性
            hypothesis_text = str(output.hypothesis)  # 提取该属性
        elif hasattr(output, "content"):  # 如果有 content 属性
            hypothesis_text = str(output.content)  # 提取该属性
        else:  # 其他情况
            hypothesis_text = str(output)  # 强制转成字符串
        return {"hypothesis": hypothesis_text}  # 返回更新字典
