from __future__ import annotations
from .state import State
from typing import Literal, Union, cast, Any
from langchain_core.messages import AIMessage
import logging
import json

logger = logging.getLogger(__name__)

# 节点路由类型定义

NodeType = Literal['Visualization', 'Search', 'Coder', 'Report', 'Process', 'NoteTaker', 'Hypothesis', 'QualityReview']
ProcessNodeType = Literal['Coder', 'Search', 'Visualization', 'Report', 'Process', 'Refiner']

def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
	""" StatePydantic  dict

	Args:
		state: 当前工作流状态，可以是 Pydantic State 对象或普通字典。
		key: 要读取的属性名。
		default: 属性不存在时的默认值。

	Returns:
		属性值或默认值。
	"""
	if isinstance(state, dict):
		return state.get(key, default)
	return getattr(state, key, default)


def hypothesis_router(state: State) -> NodeType:
	"""
	"""
	print(f"[DEBUG] hypothesis_router: hypothesis={getattr(state, 'hypothesis', None)}, current_instruction={getattr(state, 'current_instruction', None)}")

	logger.info("Entering hypothesis_router")
	current_instruction = get_state_attr(state, "current_instruction")

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Hypothesis router",
		extra={"session_id": session_id[:8], "hypothesis": getattr(state, "hypothesis", None), "current_instruction": current_instruction, "decision": "Process" if current_instruction == "Continue the research process" else "Hypothesis"}
	)

	if current_instruction == "Continue the research process":
		return "Process"
	else:
		return "Hypothesis"


def human_wait_review_router(state: State) -> str:
	"""HumanReview  needs_revision 
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

	- needs_revision=False → NoteTaker
	"""
	logger.info("Entering QualityReview_router")
	messages = get_state_attr(state, "messages", [])
	needs_revision = get_state_attr(state, "needs_revision", False)
	revision_count = get_state_attr(state, "revision_count", 0)
	MAX_REVISIONS = 3

	if needs_revision:
		if revision_count > MAX_REVISIONS:
			logger.warning(f"Max revisions ({MAX_REVISIONS}) reached. Forcing progression to NoteTaker.")
			return "NoteTaker"


		previous_node = messages[-2].name if len(messages) >= 2 else "NoteTaker"
		revision_routes = {
			"visualization_agent": "Visualization",
			"search_agent": "Search",
			"code_agent": "Coder",
			"report_agent": "Report"
		}
		result = revision_routes.get((str(previous_node)), "NoteTaker")
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
		return "NoteTaker"


def process_router(state: State) -> ProcessNodeType:
	"""
	"""
	logger.info("Entering process_router")
	next_step = get_state_attr(state, "next_workflow_step", "")

	valid_decisions = {"Coder", "Search", "Visualization", "Report"}

	if next_step in valid_decisions:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": next_step}
		)
		return cast(ProcessNodeType, next_step)

	if next_step == "FINISH":
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Refiner"}
		)
		return "Refiner"

	# 安全措施：步数过多时强制结束
	step_count = get_state_attr(state, "step_count", 0)
	if step_count > 20:
		session_id = get_state_attr(state, "session_id", "unknown")
		logger.info(
			"Process router",
			extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Refiner"}
		)
		return "Refiner"

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Process router",
		extra={"session_id": session_id[:8], "next_step": next_step, "decision": "Process"}
	)
	return "Process"


def main_router(state: State) -> str:
	"""
	"""
	logger.info("Entering main_router")
	messages = get_state_attr(state, "messages", [])
	if not messages:
		return "Analysis"

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

	session_id = get_state_attr(state, "session_id", "unknown")
	logger.info(
		"Main router",
		extra={"session_id": session_id[:8], "user_text": user_text, "chat_score": chat_score, "analysis_score": analysis_score, "decision": "Chat (default, no keywords matched)"}
	)
	return "Chat"


logger.info("Router module initialized")
