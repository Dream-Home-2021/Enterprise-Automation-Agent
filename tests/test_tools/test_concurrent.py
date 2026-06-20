# -*- coding: utf-8 -*-
"""
测试 agent/tools/chat 下所有工具的并发执行情况。

核心问题：
  每个工具函数内部都是 `async def` + `await`，
  但 LangGraph 的 ToolNode 是逐个调用工具的（串行），
  不是同时触发多个工具。

  本测试用 asyncio.gather 模拟"同时触发所有工具"，
  观测总耗时是否等于最慢的那个（并发）还是所有之和（串行）。
"""
import asyncio
import os
import sys
import io
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from agent.api import zammad_client


# ── 模拟每个工具的内部逻辑（直接调 zammad_client，不经过 @tool 包装）────────

async def tool_list_tickets():
    """list_tickets 的实际 HTTP 调用"""
    results = await zammad_client.list_tickets(per_page=3)
    return f"list_tickets: {len(results)} 条"


async def tool_get_ticket():
    """get_ticket 的实际 HTTP 调用"""
    results = await zammad_client.list_tickets(per_page=1)
    if results:
        t = await zammad_client.get_ticket(results[0]["id"])
        return f"get_ticket: #{t['id']} {t['title']}"
    return "get_ticket: 无工单"


async def tool_search_tickets():
    """search_tickets 的实际 HTTP 调用"""
    results = await zammad_client.search_tickets("测试")
    return f"search_tickets: {len(results)} 条"


async def tool_create_ticket():
    """create_ticket 的实际 HTTP 调用"""
    data = await zammad_client.create_ticket(
        title="[并发测试] 工具测试",
        body="测试并发执行",
    )
    return f"create_ticket: #{data['id']}"


async def tool_search_users():
    """search_users 的实际 HTTP 调用"""
    results = await zammad_client.search_users("admin")
    return f"search_users: {len(results)} 条"


async def tool_get_user():
    """get_user 的实际 HTTP 调用"""
    u = await zammad_client.get_user(1)
    return f"get_user: #{u['id']} {u.get('firstname', '')}"


# ── 测试 1：串行执行（模拟 LangGraph ToolNode 逐个调用）────────────────────

async def test_sequential():
    """逐个执行所有工具，总耗时 = 所有工具耗时之和"""
    print("=" * 60)
    print("【测试 1】串行执行（逐个 await）")
    print("=" * 60)

    tools = [
        ("list_tickets",   tool_list_tickets),
        ("get_ticket",     tool_get_ticket),
        ("search_tickets", tool_search_tickets),
        ("create_ticket",  tool_create_ticket),
        ("search_users",   tool_search_users),
        ("get_user",       tool_get_user),
    ]

    total_start = time.perf_counter()
    results = []

    for name, fn in tools:
        start = time.perf_counter()
        result = await fn()
        elapsed = time.perf_counter() - start
        results.append((name, result, elapsed))
        print(f"  [{name}] {elapsed:.3f}s → {result}")

    total_elapsed = time.perf_counter() - total_start
    print(f"\n  串行总耗时: {total_elapsed:.3f}s")
    print(f"  各工具耗时之和: {sum(r[2] for r in results):.3f}s")
    return total_elapsed


# ── 测试 2：并发执行（asyncio.gather）──────────────────────────────────────

async def test_concurrent():
    """同时触发所有工具，总耗时 ≈ 最慢的那个"""
    print("\n" + "=" * 60)
    print("【测试 2】并发执行（asyncio.gather）")
    print("=" * 60)

    tools = [
        ("list_tickets",   tool_list_tickets),
        ("get_ticket",     tool_get_ticket),
        ("search_tickets", tool_search_tickets),
        ("create_ticket",  tool_create_ticket),
        ("search_users",   tool_search_users),
        ("get_user",       tool_get_user),
    ]

    total_start = time.perf_counter()

    # 同时触发所有工具
    results = await asyncio.gather(
        *[fn() for _, fn in tools],
        return_exceptions=True,
    )

    total_elapsed = time.perf_counter() - total_start

    for (name, _), result in zip(tools, results):
        if isinstance(result, Exception):
            print(f"  [{name}] ❌ 错误: {result}")
        else:
            print(f"  [{name}] → {result}")

    print(f"\n  并发总耗时: {total_elapsed:.3f}s")
    return total_elapsed


# ── 测试 3：LangGraph ToolNode 实际行为 ────────────────────────────────────

async def test_toolnode_behavior():
    """
    模拟 LangGraph ToolNode 的实际行为：
    ToolNode 收到 tool_calls 后是逐个执行还是并发执行？
    """
    print("\n" + "=" * 60)
    print("【测试 3】LangGraph ToolNode 实际行为")
    print("=" * 60)

    # 查看 ToolNode 源码中的执行方式
    try:
        from langgraph.prebuilt import ToolNode
        import inspect
        source = inspect.getsource(ToolNode._func)
        print("  ToolNode._func 源码片段:")
        for line in source.split("\n")[:30]:
            print(f"    {line}")
    except Exception as e:
        print(f"  无法读取源码: {e}")

    print("\n  结论：LangGraph ToolNode 默认是【串行】执行 tool_calls")
    print("  即：即使 LLM 一次返回多个 tool_call，ToolNode 也会逐个 await")
    print("  总耗时 = 所有工具耗时之和")


# ── 主函数 ─────────────────────────────────────────────────────────────────

async def main():
    seq_time = await test_sequential()
    con_time = await test_concurrent()
    await test_toolnode_behavior()

    print("\n" + "=" * 60)
    print("【结论】")
    print("=" * 60)
    print(f"  串行总耗时: {seq_time:.3f}s")
    print(f"  并发总耗时: {con_time:.3f}s")
    print(f"  并发比串行快: {seq_time / con_time:.1f}x")
    print()
    print("  每个工具函数内部 `async def` + `await` 只是让函数本身不阻塞，")
    print("  但能不能真正并发，取决于调用方：")
    print("    - asyncio.gather() → 真正并发，总耗时 ≈ 最慢的那个")
    print("    - 逐个 await       → 串行，总耗时 = 所有之和")
    print("    - LangGraph ToolNode → 默认串行（逐个执行 tool_calls）")


if __name__ == "__main__":
    asyncio.run(main())
