# ============================================================
# 文件角色: src/agents/factory.py — Agent 工厂类，按名称创建 Agent 实例
# 小白导读:
#   - 工厂模式: 一种设计模式，用一个"工厂"对象来统一创建其他对象。
#   - 类比: 你告诉汽车工厂"我要 SUV"，工厂就给你一辆 SUV，你不用自己造。
# 协作关系:
#   - 被 workflow.py 或 system.py 调用，根据配置创建各种 Agent。
#   - 导入所有具体 Agent 类（VisualizationAgent、CodeAgent 等）。
# ============================================================

from .visualization_agent import VisualizationAgent  # 导入可视化 Agent
from .code_agent import CodeAgent  # 导入代码 Agent
from .search_agent import SearchAgent  # 导入搜索 Agent
from .report_agent import ReportAgent  # 导入报告 Agent
from .quality_review_agent import QualityReviewAgent  # 导入质量审查 Agent
from .refiner_agent import RefinerAgent  # 导入优化 Agent
from .hypothesis_agent import HypothesisAgent  # 导入假设生成 Agent
from .process_agent import ProcessAgent  # 导入流程 Agent
from .note_agent import NoteAgent  # 导入笔记 Agent
from .chat_agent import ChatAgent  # 导入工单操作 Agent
from ..config import WORKING_DIRECTORY  # 导入工作目录配置

class AgentFactory:
    """Agent 工厂：按名称创建对应的 Agent 实例。
    小白导读: 给一个名字（如 "code_agent"），返回对应的 Agent 对象。
    假数据示例:
        输入: agent_name = "code_agent"
        返回: CodeAgent(language_model_manager=..., team_members=..., ...)
    """

    def __init__(self, language_model_manager, team_members, working_directory=WORKING_DIRECTORY):
        self.language_model_manager = language_model_manager  # 保存语言模型管理器
        self.team_members = team_members  # 保存团队成员列表
        self.working_directory = working_directory  # 保存工作目录

    def create_agent(self, agent_name: str):
        """根据名称创建 Agent 实例。
        小白导读: 通过字典映射找到对应的类，然后实例化。
        """
        # 名字 -> 类 的映射表
        agent_mapping = {
            "visualization_agent": VisualizationAgent,  # 可视化 Agent
            "code_agent": CodeAgent,  # 代码 Agent
            "search_agent": SearchAgent,  # 搜索 Agent
            "report_agent": ReportAgent,  # 报告 Agent
            "quality_review_agent": QualityReviewAgent,  # 质量审查 Agent
            "refiner_agent": RefinerAgent,  # 优化 Agent
            "hypothesis_agent": HypothesisAgent,  # 假设生成 Agent
            "process_agent": ProcessAgent,  # 流程 Agent
            "note_agent": NoteAgent,  # 笔记 Agent
		    "chat_agent": ChatAgent,  # 工单操作 Agent
        }
        agent_class = agent_mapping.get(agent_name)  # 根据名字查找对应的类
        if not agent_class:  # 如果找不到
            raise ValueError(f"Agent '{agent_name}' not implemented.")  # 抛出错误
        # 实例化并返回，传入三个公共参数
        return agent_class(
            language_model_manager=self.language_model_manager,
            team_members=self.team_members,
            working_directory=self.working_directory
        )
