# =============================================================================
# 文件角色: VisualizationAgent —— 数据可视化的"图表设计师"
# 小白导读:
#   - Visualization: 可视化，把数据变成图表（折线图、柱状图、热力图等）
#   - execute_code: 执行 Python 代码，通常用来调 matplotlib/seaborn/plotly 画图
#   - execute_command: 执行系统命令，如运行脚本、安装依赖
#   - data_viz_artifacts: State 中存储所有可视化产物的"文件夹"
# 协作关系:
#   - 接收报告产物（来自 ReportAgent），从中提取数据生成图表
#   - 输出 ArtifactSchema 格式的产物（图片文件路径 + 描述）
#   - 通常是工作流中倒数第二步，最后 ProcessAgent 输出 FINISH 结束
# =============================================================================

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
    """负责创建数据可视化的 Agent。"""

    def __init__(self, language_model_manager: "LanguageModelManager", team_members: List[str], working_directory: str = WORKING_DIRECTORY):
        """初始化 VisualizationAgent。

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
        # 小白导读: 产物格式为 ArtifactSchema，包含 artifacts 字段（图片路径 + 描述）
        self.response_format = ArtifactSchema

    def _get_tools(self) -> List:
        """获取数据可视化所需的工具列表。"""
        # 小白导读: 图表设计师需要读报告 + 执行 Python 代码画图 + 列目录查看结果
        return [read_document, execute_code, execute_command, list_directory]

    def get_state_updates(self, state: "State", output: Any) -> Dict[str, Any]:
        """返回可视化产物的 State 更新。"""
        # 小白导读: safe_get 安全取值，兼容 dict 和 Pydantic 对象
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # 小白导读: 读取已有的可视化产物，与新产物合并
        current = get_state_attr(state, "data_viz_artifacts", {})
        new_data = safe_get(output, "artifacts", output)
        # 小白导读: update_artifact_dict 把新图表合并到已有产物字典
        return {"data_viz_artifacts": update_artifact_dict(current, new_data)}
