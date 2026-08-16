"""
Agent专用结构化日志模块。

7个关键日志点（生命周期→决策→LLM→工具→状态→异常→性能）：
    - request_start: 请求开始
    - request_end: 请求结束
    - node_enter: 节点进入
    - node_exit: 节点退出
    - router_decision: 路由决策
    - llm_invoke: LLM调用
    - tool_call: 工具调用
    - state_change: 状态变更
    - fallback: 降级处理
"""
import logging
import time
from typing import Any
from utils.log import get_logger

# 基于现有 logger，创建 agent 专用 logger
logger = get_logger("agent")


def request_start(session_id: str, user_id: int, msg_preview: str, history_len: int = 0):
    """请求开始 - 记录会话信息"""
    logger.info(
        "Request started",
        extra={"session_id": session_id[:8], "user_id": user_id, "msg_preview": msg_preview[:50], "history_len": history_len}
    )


def request_end(session_id: str, duration: float, steps: int = 0, status: str = "success"):
    """请求结束 - 记录耗时和状态"""
    logger.info(
        "Request ended",
        extra={"session_id": session_id[:8], "duration": round(duration, 2), "steps": steps, "status": status}
    )


def node_enter(session_id: str, node_name: str, step_count: int = 0, messages_len: int = 0):
    """节点进入 - 记录当前步数和消息数"""
    logger.info(
        "Node entered",
        extra={"session_id": session_id[:8], "node_name": node_name, "step_count": step_count, "messages_len": messages_len}
    )


def node_exit(session_id: str, node_name: str, duration: float = 0):
    """节点退出 - 记录耗时"""
    logger.info(
        "Node exited",
        extra={"session_id": session_id[:8], "node_name": node_name, "duration": round(duration, 2)}
    )


def router_decision(session_id: str, router_name: str, from_node: str, decision: str, reason: str = ""):
    """路由决策 - 记录路由决策结果"""
    logger.info(
        "Router decision made",
        extra={"session_id": session_id[:8], "router_name": router_name, "from_node": from_node, "decision": decision, "reason": reason}
    )


def llm_invoke(agent_name: str, model: str, input_tokens: int = 0, timeout: int = 60):
    """LLM调用 - 记录模型和token信息"""
    logger.info(
        "LLM invoke",
        extra={"agent_name": agent_name, "model": model, "input_tokens": input_tokens, "timeout": timeout}
    )


def llm_response(agent_name: str, output_tokens: int = 0, cost: float = 0):
    """LLM响应 - 记录输出token和成本"""
    logger.info(
        "LLM response",
        extra={"agent_name": agent_name, "output_tokens": output_tokens, "cost": cost}
    )


def tool_call(agent_name: str, tool_name: str, args_preview: str = ""):
    """工具调用开始"""
    logger.info(
        "Tool called",
        extra={"agent_name": agent_name, "tool_name": tool_name, "args_preview": args_preview[:50]}
    )


def tool_result(agent_name: str, tool_name: str, result_preview: str = ""):
    """工具调用结果"""
    logger.info(
        "Tool result",
        extra={"agent_name": agent_name, "tool_name": tool_name, "result_len": len(result_preview)}
    )


def state_change(session_id: str, field: str, old_val: str = "", new_val: str = ""):
    """关键状态变更 - 记录重要字段变化"""
    logger.info(
        "State changed",
        extra={"session_id": session_id[:8], "field": field, "old_value": old_val[:30], "new_value": new_val[:30]}
    )


def fallback(session_id: str, from_component: str, to_component: str, reason: str):
    """降级处理 - 记录组件降级"""
    logger.warning(
        "Fallback triggered",
        extra={"session_id": session_id[:8], "from_component": from_component, "to_component": to_component, "reason": reason}
    )


def error(session_id: str, node_name: str, error_type: str, error_msg: str):
    """错误记录 - 便于异常分析"""
    logger.error(
        "Node error",
        extra={"session_id": session_id[:8], "node_name": node_name, "error_type": error_type, "error_msg": error_msg}
    )


# ============ Context Manager for Auto Timing ============

from contextlib import contextmanager

@contextmanager
def log_node(node_name: str, session_id: str = "unknown"):
    """节点耗时自动记录 context manager"""
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        logger.info(
            "Node duration",
            extra={"session_id": session_id[:8], "node_name": node_name, "duration": round(elapsed, 2)}
        )