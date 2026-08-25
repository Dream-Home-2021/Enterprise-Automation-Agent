from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.messages import BaseMessage, HumanMessage
# LangGraph 提供的消息合并器——新消息进来时自动 append，不会覆盖旧消息

from langgraph.graph.message import add_messages


class State(BaseModel):


	"""
	"""

	# --- Pydantic 全局配置 ---
	model_config = ConfigDict(
		arbitrary_types_allowed=True,
		# 校验参数
		validate_assignment=True,
		# 未声明的字段忽略
		extra='ignore'
	)



	messages: Annotated[list[BaseMessage], add_messages] = Field(
		default_factory=list,
		description="工作流中交换的消息序列"
	)

	# 最近一次执行动作的 Agent —— 相当于"此刻谁在工位上"的下标签
	last_active_agent: str | None = Field(
		default=None,
		description="最近一次执行动作的 Agent 名称"
	)


	step_count: int = Field(
		default=0,
		description="安全计数器，防止无限循环"
	)

	current_instruction: str | None = Field(
		default=None,
		description="分配给下一个 Agent 的具体任务"
	)


	next_workflow_step: str | None = Field(
		default=None,
		description="下一个要路由到的节点/Agent 名称"
	)

	todo_list: list[str] = Field(
		default_factory=list,
		description="待完成的子任务列表"
	)

	completed_tasks: list[str] = Field(
		default_factory=list,
		description="已完成的子任务列表"
	)

	# ===== 领域产物：各 Agent 的"作品展览柜" =====


	# 当前的研究假设——Hypothesis Agent 填写的科学猜想 / 问题的初步定义
	hypothesis: str | None = Field(
		default=None,
		description="当前研究假设"
	)

	search_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="搜索结果的 {路径: 摘要} 映射"
	)

	# 可视化产物——Visualization Agent 画的图、生成的 HTML 仪表盘
	data_viz_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="可视化产物的 {路径: 摘要} 映射"
	)

	code_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="代码文件的 {路径: 摘要} 映射"
	)

	report_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="报告章节的 {章节: 路径/内容} 映射"
	)



	quality_feedback: str | None = Field(
		default=None,
		description="质量审查的反馈内容"
	)

	# 返工信号——True = 质检不通过，Refiner Agent 需要介入改稿

	needs_revision: bool = Field(
		default=False,
		description="触发修订循环的标志位"
	)

	# 已经连续修订了几次——防止返工无限循环

	revision_count: int = Field(
		default=0,
		description="连续修订尝试的计数器"
	)



	active_mode: str | None = Field(
		default=None,
		description="当前工作模式: chat | analysis"
	)

	chat_response: str | None = Field(
		default=None,
		description="ChatAgent 的回复内容"
	)