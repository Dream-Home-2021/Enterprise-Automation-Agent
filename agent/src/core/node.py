# =============================================================================
# 文件角色: src/core/node.py
# 本文件是"节点执行层"——LangGraph 工作流中每个节点的具体实现。
# 它负责"调用 Agent → 拿到结果 → 更新 State"这个核心循环。
#
# 小白导读:
# - LangGraph: 用来给 Agent 编排"流程图"的库，节点是图上的"站"，边是"路"。
# - State: 整个工作流中流动的"记忆包"，像一个会传递的笔记本，所有节点共享。
# - Agent: 一个能自主决策、调用工具、完成任务的"智能体"。
# - LLM: Large Language Model，大语言模型，比如 GPT、Claude。
# - MCP: Model Context Protocol，让 LLM 能调用外部工具的"手和眼"协议。
# - Artifact: Agent 产出的"产物"，比如生成的文件、报告、图表。
# - Pydantic: Python 里给数据加"类型约束"的库，类似表单校验。
# - AIMessage / HumanMessage: LangChain 里的消息类型，分别代表 AI 说的话和用户说的话。
#
# 协作关系:
# - 被 src/core/workflow.py 调用，用来构建 LangGraph 图。
# - 依赖 src/core/state.py 里的 State 类型。
# - 依赖 src/agents/base.py 里的 BaseAgent 接口。
# - 依赖 src/config.py 里的 WORKING_DIRECTORY 决定文件存到哪里。
# =============================================================================

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

from .state import State  # 导入 State 类型，用于类型提示；State 是整个工作流的"记忆包"
from ..config import WORKING_DIRECTORY  # 工作目录路径，所有产物文件默认存这里

# TYPE_CHECKING 块里的导入只给类型检查器（如 mypy、IDE）看，运行时不会真的 import
# 这样做是为了避免循环导入（A 调 B，B 又调 A）
# 校验后发现下面两个文件没用互相import的情况，所以不存在报错情况，代码多余
if TYPE_CHECKING:
    from .state import State
    from ..agents.base import BaseAgent

# 获取当前模块的 logger，日志会打印出"core.node"这样的来源，但是root被封锁，所以借用src管道，实际情况src.core.node
logger = logging.getLogger(__name__)

# 需要监控的关键状态字段
WATCHED_FIELDS = [
    "messages", "last_active_agent", "step_count", "current_instruction",
    "next_workflow_step", "todo_list", "completed_tasks", "hypothesis",
    "search_artifacts", "data_viz_artifacts", "code_artifacts", "report_artifacts",
    "quality_feedback", "needs_revision", "revision_count", "active_mode",
    "chat_response"
]


# 从state读取数据       | ：state或diec都可以    key顾名思义   default：没找到时自定义返回的值，默认none
def get_state_attr(state: State | dict[str, Any], key: str, default: Any = None) -> Any:
    """安全地从 State（Pydantic 或 dict）中 读取 属性。

    小白导读: State 是 Pydantic 模型，但有时也会被当成普通 dict 传来传去。
    这个函数兼容两种情况，避免 KeyError 或 AttributeError。

    假数据示例:
        state = {"revision_count": 3, "query": "分析数据"}
        get_state_attr(state, "revision_count", 0)  -> 3
        get_state_attr(state, "不存在的键", "默认值")  -> "默认值"
    """
    if isinstance(state, dict):
        return state.get(key, default) # 用 dict 的方式取
    return getattr(state, key, default) # 用属性的方式取


def update_artifact_dict(current_artifacts: dict[str, str], new_output: dict[str, str] | str | Any) -> dict[str, str]:
    """
    将新的 Agent 输出合并到现有产物字典中。
    - 如果是 dict，直接合并。
    - 如果是 str（旧格式），用时间戳生成键名保存。

    小白导读: Artifact（产物）是 Agent 产出的成果，比如生成的报告文件。
    这里用 dict 来管理，key 是文件名，value 是内容或路径。

    假数据示例:
        current = {"report.md": "..."}
        update_artifact_dict(current, {"chart.png": "..."})
        -> {"report.md": "...", "chart.png": "..."}
    """
    # 先复制一份，避免修改原 dict（防御性拷贝）
    updated = current_artifacts.copy() if current_artifacts else {}

    if isinstance(new_output, dict):
        # dict 格式：直接合并，新 key 覆盖旧 key
        updated.update(new_output)
    elif isinstance(new_output, str) and new_output:
        # 兜底：为原始字符串输出生成带时间戳的键
        timestamp = int(time.time())
        key = f"output_{timestamp}.txt"
        # 只保存前 100 个字符作为摘要，避免 dict 过大
        summary = new_output[:100] + "..." if len(new_output) > 100 else new_output
        updated[key] = summary

    return updated


def safe_get_content(output: Any, keys: list[str], default: str = "") -> str:
    """从各种格式的输出中安全提取文本内容。

    小白导读: Agent 返回的输出可能是 str、dict、或者某个对象，格式不统一。
    这个函数统一处理，按 keys 列表依次尝试，找到就返回。

    假数据示例:
        safe_get_content({"content": "你好"}, ["content", "text"]) -> "你好"
        safe_get_content("直接是字符串", ["content"])           -> "直接是字符串"
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
    """从文本中提取并解析 JSON（支持 markdown 代码块）。

    小白导读: LLM 返回的内容经常"不纯"——前面可能带一句说明，或者用 Markdown 代码块包裹。
    这个函数负责从"杂乱文本"里把 JSON 扣出来。

    假数据示例:
        extract_json_from_text('{"key": "value"}')                      -> {"key": "value"}
        extract_json_from_text('结果是 ```json\n{"a":1}\n```')          -> {"a": 1}
        extract_json_from_text('分析完成，数据为 {"x": 2}，请查看。')   -> {"x": 2}
    """
    if not text:
        return None

    # 优先匹配 ```json ... ``` 块
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            # group(1) 是括号里捕获的内容
            return json.loads(json_match.group(1))
        # 代码块里的内容不是合法 JSON，继续往下试
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
    """从 Agent 结果中提取结构化输出，附带多种回退解析策略。

    小白导读: Agent 返回的 result 可能是 dict、Pydantic 对象、带 messages 的字典、
    或者纯字符串。这个函数按优先级尝试各种"开箱"方式，把核心数据取出来。

    假数据示例:
        get_structured_output({"structured_response": {"step": 1}}, agent) -> {"step": 1}
        get_structured_output("纯文本", agent)                            -> None
    """
    # 1. result 本身就是 dict 且包含 structured_response
    if isinstance(result, dict) and "structured_response" in result:
        return result["structured_response"]

    # 2. result 本身可能是 Pydantic 对象
    if hasattr(result, "dict") or hasattr(result, "model_dump"):
        return result

    # 3. 从最后一条消息内容中解析 JSON
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
    通用节点执行器：调用 Agent → 提取输出 → 更新 State。
    所有"工作角色"节点（Coder/Search/Viz/Report 等）共用此函数。

    小白导读: 这是整个工作流的"心脏"——每个节点都走这个流程：
    1. 把 State 喂给 Agent
    2. Agent 返回结果
    3. 从结果里提取有用信息
    4. 把信息写回 State

    假数据示例:
        agent_node(state, some_agent, "search")
        -> {"messages": [...新消息...], "last_active_agent": "search", "step_count": 5, ...}
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
        # print(result)

        # 鲁棒的结构化输出提取
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

        # 基础更新：追加消息 + 记录活跃 Agent
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

        # 递增工作流步数计数器
        current_step = get_state_attr(state, "step_count", 0)
        updates["step_count"] = current_step + 1

        # 追踪和添加已完成的任务（用于进度监控）
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
        # 出错时记录日志，并返回一条包含错误信息的消息，避免工作流崩溃
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        current_messages = list(get_state_attr(state, "messages", []))
        return {
            "messages": current_messages + [AIMessage(content=f"Error: {str(e)}", name=name)],
            "last_active_agent": name
        }


#
def human_choice_node(state: State) -> dict[str, Any]:
    """人工选择节点：使用 interrupt() 真正暂停 graph，等待用户选择后恢复。

    工作流：
      1. 首次进入：调用 interrupt(options_data) → graph 真正暂停
      2. 前端通过 SSE 收到中断事件 → 弹出选择对话框
      3. 用户选择后前端调用 resume API → Command(resume=choice_data) 恢复 graph
      4. interrupt() 返回 choice_data → 处理选择 → 返回 state 更新
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

    # interrupt() 真正暂停 graph 执行
    # 前端收到 options_data 后弹出对话框，用户选择后通过 Command(resume=choice_data) 恢复
    # 恢复后，interrupt() 调用返回 choice_data
    choice_data = interrupt(options_data)

    # --- 恢复后：处理用户选择 ---
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
    """CLI 模式下阻塞 stdin 读取选择（保持向后兼容）。"""
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
    """根据消息类型创建 BaseMessage 对象。

    小白导读: 消息可能是 dict 也可能是对象，这个函数统一转成 LangChain 能识别的 BaseMessage。

    假数据示例:
        create_message({"content": "你好", "type": "human"}, "agent") -> HumanMessage("你好")
        create_message({"content": "回复", "type": "ai"}, "agent")     -> AIMessage("回复", name="agent")
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
    NoteAgent 专用节点：负责上下文窗口管理（裁剪中间消息）+ 全量状态更新。
    NoteAgent 会读取所有产物文件，生成摘要并压缩消息历史。

    小白导读: 当对话太长时，NoteAgent 会"裁剪"中间的消息，只保留首尾，
    避免超过 LLM 的上下文窗口限制（类似手机后台清理）。

    假数据示例:
        note_agent_node(state, note_agent, "note_agent")
        -> {"messages": [...压缩后的消息...], "hypothesis": "...", ...}
    """
    logger.info(f"Processing note agent: {name}")
    try:
        # 安全读取messages属性的值，没有则为空list
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

        # 构造 dict 状态传给 Agent
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

        # 把 NoteAgent 的输出映射回 State 各字段
        new_messages_data = safe_get(output, "messages", [])
        new_messages = [create_message(msg, name) for msg in new_messages_data] if isinstance(new_messages_data, list) else []
        messages: list[BaseMessage] = list(new_messages) if new_messages else list(processing_messages)
        combined_messages = head_messages + messages + tail_messages

        updated_state = {
            "messages": combined_messages,
            "hypothesis": str(safe_get(output, "hypothesis", "")),

            # 语义映射  别看这么长，实际就是str(output)
            "current_instruction": str(safe_get(output, "current_instruction", safe_get(output, "process", ""))),
            "next_workflow_step": str(safe_get(output, "next_workflow_step", safe_get(output, "process_decision", ""))),

            # 产物映射   别看这么长，实际就是  update_artifact_dict({}, output)
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
    """发生异常时构造错误状态。

    小白导读: 内部辅助函数，把错误信息打包成 State 格式的 dict 返回。
    前缀 _ 表示这是"私有函数"，不建议外部直接调用。
    """
    logger.info(f"Creating error state for {name}: {error_type}")

    current_dict = state.dict() if hasattr(state, "dict") else dict(state)
    current_dict["messages"] = list(get_state_attr(state, "messages", [])) + [error_message]
    current_dict["last_active_agent"] = name

    return current_dict


def human_review_node(state: State, config: RunnableConfig | None = None) -> dict[str, Any]:
    """
    人工审核节点：使用 interrupt() 真正暂停 graph，等待用户审核后恢复。

    工作流：
      1. 首次进入：调用 interrupt(options_data) → graph 真正暂停
      2. 前端通过 SSE 收到中断事件 → 弹出审核对话框
      3. 用户选择后前端调用 resume API → Command(resume=choice_data) 恢复 graph
      4. interrupt() 返回 choice_data → 处理选择 → 返回 state 更新
    """
    import os
    # CLI 模式：走 stdin（兼容旧用法）
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

    # --- 恢复后：处理用户选择 ---
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
    """CLI 模式下阻塞 stdin 读取选择（保持向后兼容）。"""
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
    """Refiner 节点：汇总工作目录中的 .md 文件，交给 RefinerAgent 精炼。

    小白导读: Refiner 是"打磨师"，负责把各个 Agent 产出的草稿合并、润色、去重。
    这个节点先把所有 .md 文件读出来拼成一个大字符串，再喂给 Agent。

    假数据示例:
        refiner_node(state, refiner_agent, "refiner")
        -> {"messages": [...精炼后的内容...], "last_active_agent": "refiner"}
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

        # 构造 Refiner 输入
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