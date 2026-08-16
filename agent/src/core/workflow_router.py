# ==========================================================================
# 文件角色：工作流路由器（Router）—— 整个工作流的"交通指挥员"
# 小白导读：
#   - Router（路由器）：根据当前状态决定下一步走哪条路，类比导航仪。
#   - State（状态）：整个工作流的"记忆本"，记录当前进度、任务列表、修订次数等。
#   - Agent（智能体）：干活的"工人"，Router 决定调用哪个 Agent 或是否结束。
#   - LLM（大语言模型）：Agent 的"大脑"，负责理解任务和生成内容。
#   - Workflow（工作流）：整体流程的"流水线"，Router 是其中的分拣开关。
#   - Pydantic：用于定义 State 数据结构的校验框架，确保状态字段类型正确。
#   - NoteTaker：记录员 Agent，负责整理和汇总研究成果。
#   - QualityReview：质量审查 Agent，负责检查产出是否达标。
#   - Hypothesis：假设生成 Agent，负责提出研究假设。
#   - Refiner：精炼 Agent，负责最终打磨产出。
# 协作关系：
#   - 被 workflow.py 调用，接收 State，返回路由决策字符串。
#   - 依赖 state.py 中的 State 类读取状态字段。
#   - 不直接调用 Agent，只返回决策字符串供 workflow 使用。
# ==========================================================================

from __future__ import annotations  # 支持 Python 3.7+ 的类型注解前向引用
from .state import State  # 导入工作流状态类
from typing import Literal, Union, cast, Any  # Literal 用于限定字符串取值，cast 用于类型强制转换
from langchain_core.messages import AIMessage  # LangChain 的 AI 消息类型，用于构建对话
import logging  # 标准日志模块
import json  # JSON 序列化模块

# 设置日志，__name__ 是当前模块名，方便追踪日志来源
logger = logging.getLogger(__name__)

# 节点路由类型定义
# 小白导读: Literal 是类型注解，限定字符串只能取这些值，类比选择题的选项列表
NodeType = Literal['Visualization', 'Search', 'Coder', 'Report', 'Process', 'NoteTaker', 'Hypothesis', 'QualityReview']
ProcessNodeType = Literal['Coder', 'Search', 'Visualization', 'Report', 'Process', 'Refiner']

def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
	"""安全地从 State（Pydantic 或 dict）中读取属性。

	假数据示例：
		输入: state=State(revision_count=2), key="revision_count", default=0
		输出: 2

		输入: state={"revision_count": 2}, key="revision_count", default=0
		输出: 2

		输入: state=State(), key="nonexistent", default="fallback"
		输出: "fallback"

	Args:
		state: 当前工作流状态，可以是 Pydantic State 对象或普通字典。
		key: 要读取的属性名。
		default: 属性不存在时的默认值。

	Returns:
		属性值或默认值。
	"""
	if isinstance(state, dict):
		return state.get(key, default)  # 字典用 .get() 安全读取
	return getattr(state, key, default)  # Pydantic 对象用 getattr 读取属性


def hypothesis_router(state: State) -> NodeType:
	"""
	假设路由器：根据 current_instruction 决定是重新生成假设还是继续研究。

	假数据示例：
		输入: State(current_instruction="Continue the research process")
		输出: "Process"

		输入: State(current_instruction="Generate new hypothesis")
		输出: "Hypothesis"

	- "Continue the research process" → Process（继续研究流程）
	- 其他 → Hypothesis（重新生成假设）
	"""
	print(f"[DEBUG] hypothesis_router: hypothesis={getattr(state, 'hypothesis', None)}, current_instruction={getattr(state, 'current_instruction', None)}")

	logger.info("Entering hypothesis_router")
	current_instruction = get_state_attr(state, "current_instruction")  # 小白导读: current_instruction 是当前指令，由 LLM 生成

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Hypothesis router",
		extra={"session_id": session_id[:8], "hypothesis": getattr(state, "hypothesis", None), "current_instruction": current_instruction, "decision": "Process" if current_instruction == "Continue the research process" else "Hypothesis"}
	)

	if current_instruction == "Continue the research process":
		return "Process"  # 继续研究，路由到 Process 节点
	else:
		return "Hypothesis"  # 重新生成假设，路由回 Hypothesis 节点


def human_wait_review_router(state: State) -> str:
	"""HumanReview 中断恢复后的路由器：根据 needs_revision 决定下一步。

	- needs_revision=True → Process（继续修改）
	- needs_revision=False → END（结束）
	"""
	logger.info("Entering human_wait_review_router")
	needs_revision = get_state_attr(state, "needs_revision", False)

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"HumanWait_Review router",
		extra={"session_id": session_id[:8], "needs_revision": needs_revision, "decision": "Process" if needs_revision else "END"}
	)

	if needs_revision:
		return "Process"
	else:
		return "END"


def QualityReview_router(state: State) -> str:
	"""
	质量审查路由器：根据审查结果决定下一步。

	假数据示例：
		输入: State(needs_revision=True, revision_count=1, messages=[..., AIMessage(name="code_agent")])
		输出: "Coder"  # 打回给代码 Agent 修订

		输入: State(needs_revision=True, revision_count=4, messages=[...])
		输出: "NoteTaker"  # 修订次数超限，强制推进

		输入: State(needs_revision=False)
		输出: "NoteTaker"  # 审查通过，进入记录环节

	- needs_revision=True 且 revision_count≤3 → 打回对应 Agent
	- needs_revision=True 且 revision_count>3 → 强制推进到 NoteTaker
	- needs_revision=False → NoteTaker
	"""
	logger.info("Entering QualityReview_router")
	messages = get_state_attr(state, "messages", [])  # 小白导读: messages 是对话历史，类比聊天记录
	needs_revision = get_state_attr(state, "needs_revision", False)  # 小白导读: needs_revision 是质量审查结果，True=需要修改
	revision_count = get_state_attr(state, "revision_count", 0)  # 小白导读: revision_count 是当前已修订次数，类比"改稿次数"
	MAX_REVISIONS = 3  # 最多修订 3 次，防止无限循环

	if needs_revision:
		# 超过最大修订次数，强制推进（防止无限循环）
		if revision_count > MAX_REVISIONS:
			logger.warning(f"Max revisions ({MAX_REVISIONS}) reached. Forcing progression to NoteTaker.")
			return "NoteTaker"  # 强制推进到记录员，不再继续修订

		# 根据上一条消息的发送者决定打回哪个 Agent
		# 小白导读: messages[-2] 是倒数第二条消息，.name 是发送者名称
		previous_node = messages[-2].name if len(messages) >= 2 else "NoteTaker"
		revision_routes = {
			"visualization_agent": "Visualization",  # 可视化 Agent → 路由到可视化节点
			"search_agent": "Search",  # 搜索 Agent → 路由到搜索节点
			"code_agent": "Coder",  # 代码 Agent → 路由到编码节点
			"report_agent": "Report"  # 报告 Agent → 路由到报告节点
		}
		result = revision_routes.get((str(previous_node)), "NoteTaker")  # 找不到则默认路由到 NoteTaker
		logger.info(f"Revision needed. Routing to: {result}")
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"QualityReview router",
			extra={"session_id": session_id[:8], "messages": messages, "needs_revision": needs_revision, "revision_count": revision_count, "decision": result}
		)
		return result

	else:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"QualityReview router",
			extra={"session_id": session_id[:8], "messages": messages, "needs_revision": needs_revision, "revision_count": revision_count, "decision": "NoteTaker"}
		)
		return "NoteTaker"  # 审查通过，进入记录环节


def process_router(state: State) -> ProcessNodeType:
	"""
	流程路由器：根据 next_workflow_step 决定下一个执行角色。

	假数据示例：
		输入: State(next_workflow_step="Coder")
		输出: "Coder"

		输入: State(next_workflow_step="FINISH")
		输出: "Refiner"

		输入: State(next_workflow_step="invalid_step", step_count=5)
		输出: "Process"  # 无效步骤，默认路由到 Process

		输入: State(next_workflow_step="invalid_step", step_count=25)
		输出: "Refiner"  # 步数过多，强制结束

	- 有效角色名 → 对应节点
	- "FINISH" → Refiner（精炼 Agent 做最终处理）
	- 无效且 step_count>20 → 强制 FINISH（防止无限循环）
	"""
	logger.info("Entering process_router")
	next_step = get_state_attr(state, "next_workflow_step", "")  # 小白导读: next_workflow_step 是下一步指令，由 LLM 或 Agent 设置

	valid_decisions = {"Coder", "Search", "Visualization", "Report"}  # 有效决策集合

	if next_step in valid_decisions:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": next_step}
		)
		return cast(ProcessNodeType, next_step)  # 小白导读: cast 是类型断言，告诉类型检查器这个值符合 ProcessNodeType

	if next_step == "FINISH":
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Refiner"}
		)
		return "Refiner"  # 任务完成，路由到精炼 Agent 做最终处理

	# 安全措施：步数过多时强制结束
	step_count = get_state_attr(state, "step_count", 0)  # 小白导读: step_count 是已执行的步数，类比"走了多少步"
	if step_count > 20:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Refiner"}
		)
		return "Refiner"  # 强制结束，防止工作流陷入死循环

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Process router",
		extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Process"}
	)
	return "Process"  # 无效决策默认路由到 Process 节点


def main_router(state: State) -> str:
	"""
	父图主路由器：判断用户意图，决定走 chat 路线还是 analysis 路线。

	假数据示例：
		输入: State(messages=[HumanMessage("帮我查一下工单 #123")])
		输出: "Chat"  # 工单操作，走 ChatAgent

		输入: State(messages=[HumanMessage("分析一下销售数据")])
		输出: "Analysis"  # 数据分析，走原有 Workflow

		输入: State(messages=[HumanMessage("你好")])
		输出: "Chat"  # 打招呼也走 ChatAgent

	- "Chat" → 走 ChatAgent 子图（查/创建/更新工单、搜索用户）
	- "Analysis" → 走原有 Workflow 子图（数据分析、报告生成）
	"""
	logger.info("Entering main_router")
	messages = get_state_attr(state, "messages", [])
	if not messages:
		return "Analysis"  # 无消息，默认走数据分析

	# 取用户最后一条消息
	last_msg = messages[-1]
	if hasattr(last_msg, "content"):
		user_text = str(last_msg.content)
	else:
		user_text = str(last_msg)

	# 使用关键字判断意图
	chat_keywords = [
		"工单", "ticket", "客服", "用户", "创建", "更新", "查询",
		"查一下", "帮我查", "搜索用户", "list_tickets", "create_ticket",
	]
	analysis_keywords = [
		"分析", "报告", "研究", "假设", "可视化", "图表", "生成",
		"搜索", "代码", "数据", "调研", "hypothesis", "research",
	]

	# 关键字评分
	chat_score = sum(1 for kw in chat_keywords if kw in user_text.lower())
	analysis_score = sum(1 for kw in analysis_keywords if kw in user_text.lower())

	if chat_score > 0 and chat_score >= analysis_score:

		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
		"Main router",
		extra={"session_id": session_id[:8], "user_text": user_text, "chat_score": chat_score, "analysis_score": analysis_score, "decision": "Chat"}
	)

		return "Chat"

	if analysis_score > 0:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
		"Main router",
		extra={"session_id": session_id[:8], "user_text": user_text, "chat_score": chat_score, "analysis_score": analysis_score, "decision": "Analysis"}
	)
		return "Analysis"

	# 无法判断时，默认走 ChatAgent（更通用的客服助手）
	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Main router",
		extra={"session_id": session_id[:8], "user_text": user_text, "chat_score": chat_score, "analysis_score": analysis_score, "decision": "Chat (default, no keywords matched)"}
	)
	return "Chat"


logger.info("Router module initialized")  # 模块加载时打印日志，确认路由器已初始化
