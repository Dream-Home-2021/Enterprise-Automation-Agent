# =============================================================================
# 文件角色：多智能体工作流的"共享记忆"——所有 Agent 读写的数据结构
#
# 小白导读（大白话解释）：
# - 多智能体工作流 (Multi-Agent Workflow) = 多个"打工角色"（Agent）排成流水线，
#   每个 Agent 干自己那道工序，合力完成一个大任务（比如科研报告、代码生成）。
# - 状态 (State) = 所有 Agent 共用的"工单/行李箱"——谁在干活、干了什么、产出丢哪里，
#   全部写在这里。
# - Pydantic BaseModel = Python 的数据模板，继承它就自动获得类型校验，防止字段写错。
# - LangGraph = 编排 Agent 的"导演"，负责按 State 里的 next_workflow_step 把控制权交给下一个 Agent。
# - 动作日志 (Action Log) = messages 字段，记录每一次 Agent 之间的对话。
# - 产物摘要 (Artifact Digest) = 各类 *_artifacts 字段，记录每个 Agent 的产出。
# - 审查循环 (Revision Loop) = 质检不通过时触发"返工"，needs_revision / revision_count 防止无限循环。
#
# 与其他文件的协作关系：
# - src/agents/*.py：每个 Agent 执行前读取 State 信息，执行后把"作品"写回对应字段。
# - src/core/workflow.py：LangGraph 路由层，读 next_workflow_step 决定下一个节点是谁。
# - src/core/workflow_router.py：路由器，基于当前消息和状态做调度决策（相当于"红绿灯"）。
# - create_initial_state() 被 main.py 或 workflow.py 在启动流水线时调用一次。
# =============================================================================

# Annotated 可以给类型附加元数据（比如加描述），这里备用
from typing import Annotated, Any
# ConfigModel 是 Pydantic 的全局配置开关；用来允许自定义类型、开启赋值校验
from pydantic import BaseModel, ConfigDict, Field
# LangChain 消息系统的两个基类：
#   BaseMessage = 所有消息的父类
#   HumanMessage = 人类用户发的一条消息（相当于聊天记录里一个字）
from langchain_core.messages import BaseMessage, HumanMessage
# LangGraph 提供的消息合并器——新消息进来时自动 append，不会覆盖旧消息
# 小白导读: add_messages = "把新消息贴到聊天记录末尾"的动作函数，用作状态合并策略
from langgraph.graph.message import add_messages


class State(BaseModel):
	# 小白导读: State = 整个流水线的"工单系统"，所有 Agent 读写它的字段。
	# 小白导读: Action Log = 动作日志（聊天记录）+ Artifact Digest = 产物摘要（产出存放处）
	"""
	多智能体研究工作流的规范共享状态。
	设计为 "Action Log"（动作日志）+ "Artifact Digest"（产物摘要）。
	"""

	# --- Pydantic 全局配置 ---
	# 小白导读: model_config 相当于给整个类贴了一张"特殊规则清单"
	# BaseModel 对进来的数据类型默认校验 int、str、float、bool、list、dict，其他报错
	# arbitrary_types_allowed虽然允许其他类型进来，但也只让声明的数据进来（这里声明了basemessage，如果进来的是humanmessage就被忽略）
	# 其次validate_assignment也做类型校验
	# 所以ConfigDict控制下，state允许的类型 = basemodel + 类中已经声明的类型（basemessage）
	model_config = ConfigDict(
		# 允许任意类型
		arbitrary_types_allowed=True,   # 允许basemodel让非标准类型进来（比如 LangChain 的 BaseMessage 对象）
		# 校验参数
		validate_assignment=True,        # 每次给字段赋值时都校验类型
		# 未声明的字段忽略
		extra='ignore'                  # 遇到没声明的字段直接忽略，不做存入，不报错（state.last_active_agent = 5 忽略）
	)

	# ===== 上下文层：记录"谁在干活"和"聊了多少句" =====
	# 小白导读: 这块区域相当于"历史公告栏"——所有人都看得到

	# 工作流中交换的消息序列——每次 Agent/用户说话都追加
	# Annotated + add_messages：告诉 LangGraph "新消息来了请贴到末尾"
	messages: Annotated[list[BaseMessage], add_messages] = Field(
		default_factory=list,
		description="工作流中交换的消息序列"   # 小白导读: 相当于无限长的聊天记录纸带
	)

	# 最近一次执行动作的 Agent —— 相当于"此刻谁在工位上"的下标签
	last_active_agent: str | None = Field(
		default=None,                    # None = 还没人上过班
		description="最近一次执行动作的 Agent 名称"
	)

	# 安全计数器——已经走了多少步，防止两个 Agent 互相让来让去陷入死循环
	# 小白导读: 相当于流水线上的"节拍器"，超过阈值会被强制停车
	step_count: int = Field(
		default=0,
		description="安全计数器，防止无限循环"
	)

	# ===== 工作流控制："接力棒传给谁" =====
	# 小白导读: 这块红绿灯区域由 Router 红灯绿来决定

	# 指导下一个 Agent 该干什么的具体任务文本
	current_instruction: str | None = Field(
		default=None,                    # None = 还没下任务
		description="分配给下一个 Agent 的具体任务"
	)

	# 路由目标——下一个要接手的 Agent 名字（如 "process_agent"、"code_agent"）
	# 小白导读: 相当于接力赛的"下一棒选手编号"
	next_workflow_step: str | None = Field(
		default=None,
		description="下一个要路由到的节点/Agent 名称"
	)

	# ===== 任务追踪：小目标完成情况 =====
	# 相当于"任务便利贴"：todo 贴一片、完成撕一片到 completed

	# 还没完成的子任务列表——Plan Agent 会把它砍成一堆小任务
	# 假数据: ["数据清洗", "绘制趋势图", "撰写结论"]
	todo_list: list[str] = Field(
		default_factory=list,
		description="待完成的子任务列表"
	)

	# 已完成子任务列表——队长贴在墙上的"已完成"清单
	completed_tasks: list[str] = Field(
		default_factory=list,
		description="已完成的子任务列表"
	)

	# ===== 领域产物：各 Agent 的"作品展览柜" =====
	# 小白导读: 这块区域相当于车间的"成品仓库"，每个 Agent 写好报告就丢进对应窗口

	# 当前的研究假设——Hypothesis Agent 填写的科学猜想 / 问题的初步定义
	hypothesis: str | None = Field(
		default=None,
		description="当前研究假设"
	)

	# 搜索产物——Search Agent 找到的文档、网页快照；
	#   键=文件路径或关键词，值=内容或摘要
	#   假数据: {"docs/abc.txt": "该文件介绍了...", "关键词:XX": "..."}
	search_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="搜索结果的 {路径: 摘要} 映射"
	)

	# 可视化产物——Visualization Agent 画的图、生成的 HTML 仪表盘
	data_viz_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="可视化产物的 {路径: 摘要} 映射"
	)

	# 代码产物——Code Agent 写的脚本、notebook、或者其他可执行文件
	code_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="代码文件的 {路径: 摘要} 映射"
	)

	# 报告产物——Report Agent 汇总出来的 Markdown / PDF 章节
	report_artifacts: dict[str, str] = Field(
		default_factory=dict,
		description="报告章节的 {章节: 路径/内容} 映射"
	)

	# ===== 审查循环：质检区 =====
	# 小白导读: 质检员（Quality Review Agent）发现不合格时，在这里写返工通知

	# 质量审查反馈——返回的"返工告知书"，写清楚哪里不行、怎么改
	quality_feedback: str | None = Field(
		default=None,                    # None = 还没收到任何返工通知
		description="质量审查的反馈内容"
	)

	# 返工信号——True = 质检不通过，Refiner Agent 需要介入改稿
	# 小白导读: 相当于"红灯"，一亮就表示整个流水线要重来一轮
	needs_revision: bool = Field(
		default=False,
		description="触发修订循环的标志位"
	)

	# 已经连续修订了几次——防止返工无限循环
	# 小白导读: 相当于"最多返工 N 次"的计数器，超过阈值直接结案
	revision_count: int = Field(
		default=0,
		description="连续修订尝试的计数器"
	)

	# ===== 子图路由控制 =====
	# 小白导读: 父图根据这个字段决定走 chat 路线还是 analysis 路线

	# 当前工作模式——"chat" 或 "analysis"
	# chat: 查/创建/更新工单，走 ChatAgent
	# analysis: 数据分析/生成报告，走原有 Workflow
	active_mode: str | None = Field(
		default=None,
		description="当前工作模式: chat | analysis"
	)

	# ChatAgent 的回复文本（仅在 chat 模式下使用）
	chat_response: str | None = Field(
		default=None,
		description="ChatAgent 的回复内容"
	)

	# ===== 人类交互控制 =====
	# 使用 LangGraph interrupt() 实现人机交互，不再需要 pending_human_action 等字段
	# interrupt() 会真正暂停 graph 执行，恢复后从 interrupt() 调用处继续
	# 前端通过 SSE 收到中断事件（包含 options_data），用户选择后通过 Command(resume=choice_data) 恢复


# # def create_initial_state() -> dict[str, Any]:
# def create_initial_state(user_input: str) -> dict[str, Any]:
# 	# 小白导读: 这是"装配第一个行李箱"的工厂函数。
# 	#           任务开始流水线之前，由 main.py 调用一次，把所有字段初始化好。
# 	#
# 	# 假数据示例:
# 	#   输入:  user_input = "请帮我分析一下本地的销售数据并生成报告"
# 	#   输出:  {
# 	#       "messages": [HumanMessage("请帮我分析一下本地的销售数据并生成报告")],
# 	#       "last_active_agent": "user",
# 	#       "step_count": 0,
# 	#       "todo_list": [],
# 	#       "completed_tasks": [],
# 	#       "search_artifacts": {},
# 	#       "data_viz_artifacts": {},
# 	#       "code_artifacts": {},
# 	#       "report_artifacts": {},
# 	#       "needs_revision": False,
# 	#       "revision_count": 0,
# 	#   }
# 	#   注意：hypothesis / current_instruction / next_workflow_step / quality_feedback 没填，
# 	#         因为它们默认 None，不会出现在返回的字典里——这是 LangGraph 的"部分初始化"写法。
# 	"""
# 	工厂函数：为 LangGraph 创建一致的初始状态字典。
# 	"""


# 	# 返回一个普通 dict（而不是 State 实例），是 LangGraph 的推荐用法
# 	# 小白导读: LangGraph 内部会自动把 dict 合并成完整的 State 差值（missing 的字段保持原样）
# 	return {
# 		# 用户的第一条消息作为聊天记录起点
# 		"messages": [HumanMessage(content=user_input)],
# 		# 标记"上一个动作是用户做的"，方便第一步 Agent 知道是用户在喊话
# 		"last_active_agent": "user",
# 		# 从零开始计数
# 		"step_count": 0,
# 		# 任务清单一开始都是空的，由 Plan Agent 去填
# 		"todo_list": [],
# 		"completed_tasks": [],
# 		# 四个产物柜全部清空
# 		"search_artifacts": {},
# 		"data_viz_artifacts": {},
# 		"code_artifacts": {},
# 		"report_artifacts": {},
# 		# 质检信号关掉，返工计数清零
# 		"needs_revision": False,
# 		"revision_count": 0,
# 		# 子图路由
# 		"active_mode": None,
# 		"chat_response": None,
# 		# 注意：hypothesis、current_instruction、next_workflow_step、quality_feedback 没写，
# 		#       留空 = LangGraph 会用 default_factory / None 作为初始值
# }