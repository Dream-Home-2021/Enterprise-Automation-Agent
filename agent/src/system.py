"""

  # Web API
  system = MultiAgentSystem()
      ...
"""
import argparse
import time
from typing import AsyncIterator, Tuple, Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from . import config
from .core.workflow import WorkflowManager
from .core.language_models import LanguageModelManager
# from .core.state import create_initial_state
from utils.log import get_logger
from utils.agent_log import request_start, request_end

logger = get_logger(__name__)



def _extract_new_ai_content(
    event,
    last_seen: int = 0,
    last_content_length: int = 0,
) -> tuple[str, int, int] | None:
    """ LangGraph event  AI 
    """
    state = event[1] if isinstance(event, tuple) and len(event) == 2 else event
    if not isinstance(state, dict):
        return None

    messages = state.get("messages", [])
    if not messages:
        return None

    last = messages[-1]

    if isinstance(last, AIMessage) and last.content:
        current_content = last.content if isinstance(last.content, str) else str(last.content)
        current_length = len(current_content)

        if current_length > last_content_length:
            new_content = current_content[last_content_length:]
            new_seen = len(messages)
            return new_content, new_seen, current_length

        # 如果是新消息（数量增加了），返回完整内容
        if len(messages) > last_seen:
            new_seen = len(messages)
            return current_content, new_seen, current_length

    # 流式 chunk（tuple 形式，CLI run 场景）
    if isinstance(last, (list, tuple)):
        text = str(last[0]) if last else str(last)
        return text, len(messages), len(text)

    return None


def _get_state_from_event(event) -> dict | None:
    """ event  state dict"""
    if isinstance(event, tuple) and len(event) == 2:
        return event[1]
    if isinstance(event, dict):
        return event
    return None


_INTERRUPT_TOKEN = "__INTERRUPT__"


class MultiAgentSystem:
    """ —— 
    """

    def __init__(self, checkpointer=None):
        self.checkpointer = checkpointer
        self.lm_manager = LanguageModelManager()
        self.workflow_manager = WorkflowManager(
            lm_manager=self.lm_manager,
            working_directory=config.WORKING_DIRECTORY,
            checkpointer=checkpointer,
        )
        self.graph = self.workflow_manager.get_graph()

    # ── CLI 模式（同步） ──

    # def run(self, user_input: str) -> None:
    #     """同步流式执行，直接打印到控制台。"""
    #     logger.info("enter cli stdo")


    async def astream(
        self,
        message: str,
        session_id: str,
        user_id: int = 1,
        history: list | None = None,
    ) -> AsyncIterator[Tuple[str, list]]:
        """ token yield (content, history) 
        """
        msg = message.strip()
        if not msg:
            yield "", history or []
            return

        history = history or []

        logger.info(
            "Request started webmode",
            extra={"session_id": session_id[:8], "user_id": user_id, "对话": message[:50],
                   "history_len": len(history or [])}
        )
        start_time = time.time()


        new_message = HumanMessage(content=msg)

        config = {
            "configurable": {
                "thread_id": str(session_id),
                "user_id": user_id,
            },
            "recursion_limit": 3000,
        }

        seen = 0
        last_content_length = 0
        print(f"[DEBUG] astream config = {config}")

        state_snapshot = await self.graph.aget_state(config)

        is_resume_scenario = state_snapshot and state_snapshot.next
        has_interrupt = (
            state_snapshot and state_snapshot.tasks and
            any(hasattr(task, "interrupts") and task.interrupts
                for task in state_snapshot.tasks)
        )

        if is_resume_scenario and has_interrupt:
            logger.warning(
                "Crash recovery: auto-resuming through interrupt",
                extra={"session_id": session_id[:8], "next_nodes": str(state_snapshot.next)}
            )
            auto_resume_data = {
                "choice": "继续研究过程",
                "input_text": "",
            }
            input_data = Command(resume=auto_resume_data)

        elif is_resume_scenario:
            logger.warning(
                "Found unfinished task, resuming from checkpoint",
                extra={"session_id": session_id[:8], "next_nodes": str(state_snapshot.next)}
            )
            input_data = None

        else:
            # 正常场景（无 interrupt、无恢复）→ 传入新消息
            input_data = {"messages": [new_message]}

        try:
            async for event in self.graph.astream(
                input_data,
                config=config,
                stream_mode="values",
                subgraphs=True,
            ):
                result = _extract_new_ai_content(event, seen, last_content_length)
                if not result:
                    continue
                content, seen, last_content_length = result
                yield content, [*history, {"role": "assistant", "content": content}]

            # stream 结束，检查是否被 interrupt() 暂停
            state_snapshot = await self.graph.aget_state(config)
            if state_snapshot and state_snapshot.tasks:
                for task in state_snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_value = task.interrupts[0].value
                        logger.info(
                            "Graph interrupted",
                            extra={"session_id": session_id[:8], "interrupt_value": str(interrupt_value)[:200]}
                        )
                        yield _INTERRUPT_TOKEN, interrupt_value
                        return

            logger.info(
                "Request completed webmode",
                extra={"session_id": session_id[:8], "duration": round(time.time() - start_time, 2)}
            )
            yield "", history

        except Exception as e:
            logger.exception("[session=%s] stream error", session_id[:8])
            raise

    async def resume(
        self,
        session_id: str,
        resume_data: dict[str, Any],
        user_id: int = 1,
    ) -> AsyncIterator[Tuple[str, list]]:
        """ interrupt() 
        """
        logger.info(
            "enter resume",
            extra={"session_id": session_id[:8], "resume_data": resume_data}
        )

        config = {
            "configurable": {
                "thread_id": str(session_id),
                "user_id": user_id,
            },
            "recursion_limit": 3000,
        }

        # 用 Command(resume=...) 恢复被 interrupt() 暂停的 graph
        seen = 0
        last_content_length = 0
        history: list = []
        async for event in self.graph.astream(
            Command(resume=resume_data),
            config=config,
            stream_mode="values",
            subgraphs=True,
        ):
            result = _extract_new_ai_content(event, seen, last_content_length)
            if not result:
                continue
            content, seen, last_content_length = result
            history = history or [{"role": "assistant", "content": content}]
            yield content, history

        state_snapshot = await self.graph.aget_state(config)
        if state_snapshot and state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    yield _INTERRUPT_TOKEN, interrupt_value
                    return

        yield "", history



async def make_generate_response() -> tuple:
    """ (generate_response, system_ref) 
    """
    from agent.memory.short_term import make_checkpointer

    try:
        checkpointer = await make_checkpointer()
        logger.info("Analysis subgraph using AsyncRedisSaver")
    except Exception:
        checkpointer = None
        logger.warning("Redis unavailable, analysis subgraph falls back to MemorySaver")

    system = MultiAgentSystem(checkpointer=checkpointer)

    async def generate_response(
        message: str,
        history: list,
        session_id: str,
        user_id: int = 1,
    ):
        async for content, new_history in system.astream(
            message, session_id=session_id, user_id=user_id, history=history
        ):
            yield content, new_history

    return generate_response, system




#     os.environ["AGENT_CLI_MODE"] = "1"


#     user_input = " ".join(args.input) or input("Please enter your research topic: ")
#     system = MultiAgentSystem()
#     system.run(user_input)
