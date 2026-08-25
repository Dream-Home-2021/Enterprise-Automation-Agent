from __future__ import annotations
from typing import Any, Union, TYPE_CHECKING
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
import logging
import json
import re
from pathlib import Path
import time

from .state import State
from ..config import WORKING_DIRECTORY

if TYPE_CHECKING:
    from .state import State
    from ..agents.base import BaseAgent

logger = logging.getLogger(__name__)

WATCHED_FIELDS = [
    "messages", "last_active_agent", "step_count", "current_instruction",
    "next_workflow_step", "todo_list", "completed_tasks", "hypothesis",
    "search_artifacts", "data_viz_artifacts", "code_artifacts", "report_artifacts",
    "quality_feedback", "needs_revision", "revision_count", "active_mode",
    "chat_response"
]


# 从state读取数据       | ：state或diec都可以    key顾名思义   default：没找到时自定义返回的值，默认none
def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
    """ StatePydantic  dict  
    """
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def update_artifact_dict(current_artifacts: dict[str, str], new_output: dict[str, str] | str | Any) -> dict[str, str]:
    """
    """
    # 先复制一份，避免修改原 dict（防御性拷贝）
    updated = current_artifacts.copy() if current_artifacts else {}

    if isinstance(new_output, dict):
        updated.update(new_output)
    elif isinstance(new_output, str) and new_output:
        timestamp = int(time.time())
        key = f"output_{timestamp}.txt"
        # 只保存前 100 个字符作为摘要，避免 dict 过大
        summary = new_output[:100] + "..." if len(new_output) > 100 else new_output
        updated[key] = summary

    return updated


def safe_get_content(output: Any, keys: list[str], default: str = "") -> str:
    """
    """
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in keys:
            if key in output:
                return str(output[key])
        return str(output)

    # 如果是对象（比如 Pydantic 模型），用 getattr 按 key 取属性
    for key in keys:
        if hasattr(output, key):
            val = getattr(output, key, None)
            if val is not None:
                return str(val)
    return str(output) if output else default


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """ JSON markdown 
    """
    if not text:
        return None

    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 '{' 和最后一个 '}'
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1:
        try:
            return json.loads(text[start_idx:end_idx+1])
        except json.JSONDecodeError:
            pass

    return None


def get_structured_output(result: Any, agent: BaseAgent) -> Any:
    """ Agent 
    """
    # 1. result 本身就是 dict 且包含 structured_response
    if isinstance(result, dict) and "structured_response" in result:
        return result["structured_response"]

    # 2. result 本身可能是 Pydantic 对象
    if hasattr(result, "dict") or hasattr(result, "model_dump"):
        return result

    content = ""
    if isinstance(result, dict) and "messages" in result and result["messages"]:
        content = result["messages"][-1].content
    elif hasattr(result, "content"):
        content = result.content
    elif isinstance(result, str):
        content = result

    if content:
        parsed = extract_json_from_text(content)
        if parsed:
            return parsed

    return None


def agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """
    """
    session_id = get_state_attr(state, "session_id", "unknown")
    logger.info(
        "Node entered",
        extra={"session_id": session_id[:8], "node_name": name, "step_count": get_state_attr(state, "step_count", 0), "messages_len": len(get_state_attr(state, "messages", []))}
    )

    for field in WATCHED_FIELDS:
        val = get_state_attr(state, field)
        logger.info(
            "State changes",
            extra={'{}'.format(field): str(val)[:300] if val is not None else "None" }
        )
    try:
        # 递归函数，自己调用自己.调用 Agent 的 invoke 方法，传入当前 State，拿到结果
        result = agent.invoke(state)

        output = get_structured_output(result, agent)

        # 提取要展示给用户的文本
        if output:
            content = safe_get_content(output, ["task", "feedback", "summary", "current_instruction"])
            ai_message = AIMessage(content=content, name=name)
        else:
            # 回退：使用最后一条消息或原始结果
            if isinstance(result, dict) and "messages" in result:
                ai_message = result["messages"][-1]
                output = ai_message.content
            else:
                output = str(result)
                ai_message = AIMessage(content=output, name=name)

        current_messages = list(get_state_attr(state, "messages", []))
        updates = {
            "messages": current_messages + [ai_message],
            "last_active_agent": name
        }

        # StateUpdater Protocol：让 Agent 自己声明如何回写 State，把得到的output产物信息写道updates里
        if hasattr(agent, "get_state_updates"):
            agent_updates = agent.get_state_updates(state, output)
            if agent_updates:
                updates.update(agent_updates)

        current_step = get_state_attr(state, "step_count", 0)
        updates["step_count"] = current_step + 1

        current_instruction = get_state_attr(state, "current_instruction", None)
        if current_instruction:
            completed = list(get_state_attr(state, "completed_tasks", []))
            if current_instruction not in completed:
                completed.append(current_instruction)
                updates["completed_tasks"] = completed

        session_id = get_state_attr(state, "session_id", "unknown")
        logger.info(
            "Node exited",
            extra={"session_id": session_id[:8], "node_name": name, "step_count": current_step + 1, "messages_len": len(current_messages + [ai_message])}
        )
        return updates

    except Exception as e:
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {
            "messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name=name)],
            "last_active_agent": name
        }


def human_choice_node(state: State) -> dict[str, Any]:
    """ interrupt()  graph
    """
    import os

    # CLI 模式：走 stdin（兼容旧用法）
    if os.environ.get("AGENT_CLI_MODE"):
        return _human_choice_cli(state)

    session_id = get_state_attr(state, "session_id", "unknown")
    logger.info(
        "enter Human choice node — calling interrupt()",
        extra={"session_id": session_id[:8], "action": "waiting for user choice"}
    )

    options_data = {
        "type": "choice",
        "options": ["重新生成假设", "继续研究过程"],
        "action_id": "HumanChoice",
    }

    choice_data = interrupt(options_data)

    selected = choice_data.get("choice", "") if isinstance(choice_data, dict) else str(choice_data)
    modification_areas = choice_data.get("input_text", "") if isinstance(choice_data, dict) else ""

    current_messages = list(get_state_attr(state, "messages", []))
    updates = {
        "last_active_agent": "human",
    }

    if selected == "重新生成假设":
        updates["messages"] = current_messages + [HumanMessage(content=f"Regenerate hypothesis. Areas: {modification_areas}")]
        updates["hypothesis"] = None
        updates["current_instruction"] = None
    else:
        updates["messages"] = current_messages + [HumanMessage(content="Continue the research process")]
        updates["current_instruction"] = "Continue the research process"

    return updates


def _human_choice_cli(state: State) -> dict[str, Any]:
    """CLI  stdin """
    import sys
    print("请选择下一步:")
    print("1. 重新生成假设")
    print("2. 继续研究过程")
    choice = "2"
    if sys.stdin.isatty():
        while True:
            try:
                choice = input("请输入您的选择（1 或 2）: ")
            except (EOFError, KeyboardInterrupt):
                choice = "2"
                break
            if choice in ["1", "2"]:
                break
            print("输入无效，请重试。")
    else:
        print("[auto] 非交互模式，默认选择2（继续）")
    current_messages = list(get_state_attr(state, "messages", []))
    updates = {"last_active_agent": "human"}
    if choice == "1":
        if sys.stdin.isatty():
            try:
                modification_areas = input("指定要修改的区域: ")
            except (EOFError, KeyboardInterrupt):
                modification_areas = ""
        else:
            modification_areas = ""
        updates["messages"] = current_messages + [HumanMessage(content=f"Regenerate hypothesis. Areas: {modification_areas}")]
        updates["hypothesis"] = None
    else:
        updates["messages"] = current_messages + [HumanMessage(content="Continue the research process")]
        updates["current_instruction"] = "Continue the research process"
    return updates


def create_message(message: Any, name: str) -> BaseMessage:
    """ BaseMessage 
    """
    if isinstance(message, dict):
        content = message.get("content", "")
        message_type = str(message.get("type", "ai")).lower()
    else:
        content = getattr(message, "content", str(message))
        message_type = str(getattr(message, "type", "ai")).lower()

    return HumanMessage(content=content) if message_type == "human" else AIMessage(content=content, name=name)


def note_agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """
    """
    logger.info(f"Processing note agent: {name}")
    try:
        current_messages = list(get_state_attr(state, "messages", []))

        # ===== 上下文窗口管理 =====
        # 当消息过多时，保留首尾各 2 条，只把中间部分传给 NoteAgent
        head_messages: list[BaseMessage] = []
        tail_messages: list[BaseMessage] = []
        processing_messages = current_messages

        if len(current_messages) > 6:
            head_messages = list(current_messages[:2])
            tail_messages = list(current_messages[-2:])
            processing_messages = list(current_messages[2:-2])
            logger.debug("Trimmed messages for processing")

        invoke_state = state.dict() if hasattr(state, "dict") else dict(state)
        invoke_state["messages"] = processing_messages

        result = agent.invoke(invoke_state)
        output = get_structured_output(result, agent)

        if not output:
            logger.error(f"Note agent {name} failed to return structured response. Result: {str(result)[:500]}")
            raw_content = ""
            if isinstance(result, dict) and "messages" in result and result["messages"]:
                raw_content = result["messages"][-1].content
            elif hasattr(result, "content"):
                raw_content = result.content
            return _create_error_state(state, AIMessage(content=f"Error: Agent {name} failed to return structured response. Raw: {raw_content[:200]}", name=name), name, "Missing structured response")

        # 安全读取辅助函数
        def safe_get(obj, key, default=""):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        new_messages_data = safe_get(output, "messages", [])
        new_messages = [create_message(msg, name) for msg in new_messages_data] if isinstance(new_messages_data, list) else []
        messages: list[BaseMessage] = list(new_messages) if new_messages else list(processing_messages)
        combined_messages = head_messages + messages + tail_messages

        updated_state = {
            "messages": combined_messages,
            "hypothesis": str(safe_get(output, "hypothesis", "")),

            "current_instruction": str(safe_get(output, "current_instruction", safe_get(output, "process", ""))),
            "next_workflow_step": str(safe_get(output, "next_workflow_step", safe_get(output, "process_decision", ""))),

            "search_artifacts": update_artifact_dict({}, str(safe_get(output, "search_artifacts", safe_get(output, "searcher_state", "")))),
            "data_viz_artifacts": update_artifact_dict({}, str(safe_get(output, "data_viz_artifacts", safe_get(output, "visualization_state", "")))),
            "code_artifacts": update_artifact_dict({}, str(safe_get(output, "code_artifacts", safe_get(output, "code_state", "")))),
            "report_artifacts": update_artifact_dict({}, str(safe_get(output, "report_artifacts", safe_get(output, "report_section", "")))),

            "quality_feedback": str(safe_get(output, "quality_feedback", safe_get(output, "quality_review", ""))),
            "needs_revision": bool(safe_get(output, "needs_revision", False)),

            "last_active_agent": 'note_agent'
        }

        return updated_state

    except Exception as e:
        logger.error(f"Unexpected error in note_agent_node: {e}", exc_info=True)
        return _create_error_state(state, AIMessage(content=f"Unexpected error: {str(e)}", name=name), name, "Unexpected error")


def _create_error_state(state: State, error_message: AIMessage, name: str, error_type: str) -> dict[str, Any]:
    """
    """
    logger.info(f"Creating error state for {name}: {error_type}")

    current_dict = state.dict() if hasattr(state, "dict") else dict(state)
    current_dict["messages"] = list(get_state_attr(state, "messages", [])) + [error_message]
    current_dict["last_active_agent"] = name

    return current_dict


def human_review_node(state: State, config: RunnableConfig | None = None) -> dict[str, Any]:
    """
    """
    import os
    if os.environ.get("AGENT_CLI_MODE"):
        return _human_review_cli(state)

    session_id = get_state_attr(state, "session_id", "unknown")
    logger.info(
        "enter Human review node — calling interrupt()",
        extra={"session_id": session_id[:8], "action": "waiting for user review"}
    )

    options_data = {
        "type": "review",
        "options": ["yes", "no"],
        "action_id": "HumanReview",
        "prompt": "当前研究进展已完成，是否需要进一步的分析或修改？",
    }

    # interrupt() 真正暂停 graph 执行
    choice_data = interrupt(options_data)

    selected = choice_data.get("choice", "") if isinstance(choice_data, dict) else str(choice_data)
    review_text = choice_data.get("input_text", "") if isinstance(choice_data, dict) else ""

    current_messages = list(get_state_attr(state, "messages", []))
    updates = {
        "last_active_agent": "human",
    }

    if selected == "yes" and review_text:
        updates["messages"] = current_messages + [HumanMessage(content=review_text)]
        updates["needs_revision"] = True
    else:
        updates["needs_revision"] = False
        updates["revision_count"] = 0

    return updates


def _human_review_cli(state: State) -> dict[str, Any]:
    """CLI  stdin """
    import sys
    try:
        print("当前研究进展:")
        print(state)
        print("\n您是否需要进一步的分析或修改？？")
        user_input = 'no'
        if sys.stdin.isatty():
            while True:
                try:
                    user_input = input('输入"yes"以继续分析，或输入"no"结束研究: ').lower()
                except (EOFError, KeyboardInterrupt):
                    user_input = 'no'
                    break
                if user_input in ['yes', 'no']:
                    break
        else:
            print("[auto] 非交互模式，结束研究")
        updates: dict[str, Any] = {"last_active_agent": "human"}
        if user_input == 'yes':
            while True:
                req = input("请输入您的请求: ").strip()
                if req:
                    updates["messages"] = [HumanMessage(content=req)]
                    updates["needs_revision"] = True
                    break
        else:
            updates["needs_revision"] = False
            updates["revision_count"] = 0
        return updates
    except Exception as e:
        logger.error(f"Error in human_review: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {"messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name="human_review")]}


def refiner_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    """Refiner  .md  RefinerAgent 
    """
    try:
        storage_path = Path(WORKING_DIRECTORY)
        materials = []

        # 收集所有 .md 文件内容
        for fpath in storage_path.glob("*.md"):
             with open(fpath, "r", encoding="utf-8") as f:
                materials.append(f"MD file '{fpath.name}':\n{f.read()}")

        # 用双换行拼接，方便 Agent 区分不同文件
        combined_materials = "\n\n".join(materials)
        report_content = f"Report materials:\n{combined_materials}"

        refiner_input = state.dict() if hasattr(state, "dict") else dict(state)
        refiner_input["messages"] = [HumanMessage(content=report_content)]

        result = agent.invoke(refiner_input)
        output = result.get("messages")[-1].content

        current_messages = list(get_state_attr(state, "messages", []))
        return {
            "messages": current_messages + [AIMessage(content=output, name=name)],
            "last_active_agent": name,
        }

    except Exception as e:
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {"messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name=name)]}

# 模块加载时的日志，方便调试时确认文件已被导入
logger.info("Agent processing module initialized")