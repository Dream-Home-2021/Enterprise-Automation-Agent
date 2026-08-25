# -*- coding: utf-8 -*-
"""
进程崩溃后如何完美恢复子图 — 使用 RedisSaver 进行硬盘持久化。

这是能够挺过"进程重启"的硬核代码结构：
1. 使用 AsyncRedisSaver 替代 SqliteSaver
2. 显式编译子图（必须带 checkpointer）
3. 父图和子图使用不同的 thread_id 进行隔离恢复
"""
import asyncio
import os
from re import sub
from typing import TypedDict
import time

# Add project root to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

# 定义状态
class SubState(TypedDict):
    sub_data: str

class ParentState(TypedDict):
    parent_data: str
    child_result: str

# Redis 连接配置
REDIS_URL = os.getenv("AGENT_REDIS_URL", "redis://localhost:6380/0")


async def run_test():
    # 创建 checkpointer
    checkpointer = AsyncRedisSaver(redis_url=REDIS_URL)
    await checkpointer.setup()

    # ==========================================
    # 1. 显式编译子图（必须带 checkpointer）
    # ==========================================
    sub_builder = StateGraph(SubState)

    async def sub_step_1(state: SubState, config=None):
        print("--- [子图] 步骤 1 正在执行... ---")
        await asyncio.sleep(5)  # 等待2秒，便于在此期间强杀进程测试恢复
        return {"sub_data": state["sub_data"] + " -> 子图1过"}

    async def sub_step_2(state: SubState, config=None):
        # 假设你在这里人工用 Ctrl+C 杀掉了 Python 进程，或者程序崩溃了
        print("--- [子图] 步骤 2 正在执行... ---")
        return {"sub_data": state["sub_data"] + " -> 子图2过"}
#
	

    sub_builder.add_node("sub_step_1", sub_step_1)
    sub_builder.add_node("sub_step_2", sub_step_2)
    sub_builder.add_edge(START, "sub_step_1")
    sub_builder.add_edge("sub_step_1", "sub_step_2")
    sub_builder.add_edge("sub_step_2", END)

    # 显式编译子图
    compiled_subgraph = sub_builder.compile(checkpointer=checkpointer)

    # ==========================================
    # 2. 编译父图
    # ==========================================
    parent_builder = StateGraph(ParentState)

    async def parent_start(state: ParentState, config=None):
        return {"parent_data": state["parent_data"] + " [父开始]"}

    # 关键：在这里手动做状态桥接和独立的 Thread 隔离
    async def call_subgraph_node(state: ParentState, config=None):
        parent_thread_id = config["configurable"]["thread_id"]

        # 派生子图专用的持久化 thread_id
        sub_config = {"configurable": {"thread_id": f"{parent_thread_id}_sub"}}

        # 检查子图在 Redis 中是否有历史状态
        sub_graph_state = await compiled_subgraph.aget_state(sub_config)


        # 如果子图有 next 节点，说明之前"在子图内部崩溃了"，需要恢复
        if sub_graph_state and sub_graph_state.next:
            print(f"⚠️ 检测到子图异常中断，尝试从断点 {sub_graph_state.next} 恢复...")
			# 传入 None 触发子图从断点 Resume
            sub_result = await compiled_subgraph.ainvoke(None, sub_config)
        else:
            # 如果是第一次正常进入，才传入初始数据
            print("--- 第一次进入子图 ---")
            sub_input = {"sub_data": state["parent_data"]}
            sub_result = await compiled_subgraph.ainvoke(sub_input, sub_config)

        return {"child_result": sub_result["sub_data"]}

    parent_builder.add_node("parent_start", parent_start)
    parent_builder.add_node("call_subgraph", call_subgraph_node)
    parent_builder.add_edge(START, "parent_start")
    parent_builder.add_edge("parent_start", "call_subgraph")
    parent_builder.add_edge("call_subgraph", END)

    compiled_parent_graph = parent_builder.compile(checkpointer=checkpointer)

    # ==========================================
    # 3. 执行测试
    # ==========================================
    thread_id = "task_001"
    config = {"configurable": {"thread_id": thread_id}}

    # 执行父图
    result = await compiled_parent_graph.ainvoke(
        {"parent_data": "任务"},
        config
    )
    print(f"\n最终结果: {result}")


if __name__ == "__main__":
    asyncio.run(run_test())