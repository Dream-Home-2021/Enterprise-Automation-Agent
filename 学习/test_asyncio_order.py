"""
asyncio 内嵌异步 & 组合运行规则测试
------------------------------------
目标：理清不同组合下的执行顺序

测试场景：
1. 顺序 await（串行）
2. asyncio.gather（并发）
3. 内嵌异步（协程内调用协程）
4. 混合：gather + 内嵌
5. Task 创建与回调
6. 嵌套 gather
7. 异步生成器
8. 异步上下文管理器
9. 真实场景：模拟 agent 调用链
10. 事件循环中的同步 vs 异步
"""

import asyncio
import time
import sys

# 解决 Windows GBK 编码问题
sys.stdout.reconfigure(encoding='utf-8')

# 统一的日志格式，方便观察顺序
def log(msg):
    # 使用单调时钟，避免系统时间跳变影响观察
    try:
        loop = asyncio.get_running_loop()
        t = loop.time()
    except RuntimeError:
        t = 0.0
    print(f"[{t:>7.3f}s] {msg}")


# ============================================================
# 基础工具：模拟异步操作
# ============================================================
async def async_task(name, delay=0.1):
    """模拟一个异步任务"""
    log(f"  ▶ {name} 开始")
    await asyncio.sleep(delay)
    log(f"  ◀ {name} 完成 (耗时 {delay}s)")
    return f"{name}-result"


# ============================================================
# 测试 1: 顺序 await（串行）
# ============================================================
async def test_sequential():
    """
    规则：await 是阻塞当前协程的，只有等前一个完成才会继续下一个。
    执行顺序：A → B → C，总耗时 = sum(各任务耗时)
    """
    log("=" * 50)
    log("测试 1: 顺序 await（串行）")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    r1 = await async_task("A", 0.1)
    r2 = await async_task("B", 0.1)
    r3 = await async_task("C", 0.1)

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s (期望 ≈ 0.3s)")
    log(f"结果: {r1}, {r2}, {r3}")
    log("")


# ============================================================
# 测试 2: asyncio.gather（并发）
# ============================================================
async def test_gather():
    """
    规则：gather 同时启动所有协程，并行执行，全部完成后返回。
    执行顺序：A、B、C 几乎同时开始，总耗时 = max(各任务耗时)
    """
    log("=" * 50)
    log("测试 2: asyncio.gather（并发）")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    results = await asyncio.gather(
        async_task("A", 0.3),
        async_task("B", 0.1),
        async_task("C", 0.2),
    )

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s (期望 ≈ 0.3s，即最慢的 A)")
    log(f"结果: {results}")
    log("")


# ============================================================
# 测试 3: 内嵌异步（协程内调用协程）
# ============================================================
async def inner_task(name, delay=0.05):
    """内层协程"""
    log(f"    └ inner_task {name} 开始")
    await asyncio.sleep(delay)
    log(f"    └ inner_task {name} 完成")
    return f"inner-{name}"


async def outer_task(name, delay=0.1):
    """外层协程：内部调用其他协程"""
    log(f"  ▶ outer_task {name} 开始")
    await asyncio.sleep(delay)
    # 内嵌调用 1：直接 await
    r1 = await inner_task(f"{name}-a", 0.05)
    # 内嵌调用 2：再调用一个
    r2 = await inner_task(f"{name}-b", 0.05)
    log(f"  ◀ outer_task {name} 完成")
    return f"outer-{name}({r1},{r2})"


async def test_nested():
    """
    规则：内嵌异步 = 外层协程内部 await 内层协程。
    内层协程执行期间，外层协程挂起，控制权交还事件循环。
    其他就绪的协程（如同级 outer_task）可以在此期间运行。
    """
    log("=" * 50)
    log("测试 3: 内嵌异步（协程内调用协程）")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    # 同时启动两个 outer_task，它们内部各自内嵌 inner_task
    results = await asyncio.gather(
        outer_task("X", 0.1),
        outer_task("Y", 0.1),
    )

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s")
    log(f"结果: {results}")
    log("观察：X 和 Y 的 inner_task 会交错执行（因为内嵌 await 会 yield 控制权）")
    log("")


# ============================================================
# 测试 4: 混合 - gather + 内嵌
# ============================================================
async def mixed_task(name):
    """混合任务：先做点事，再内嵌调用"""
    log(f"  ▶ {name} 第一阶段")
    await asyncio.sleep(0.05)
    # 内嵌：并发子任务
    sub_results = await asyncio.gather(
        inner_task(f"{name}-sub1", 0.1),
        inner_task(f"{name}-sub2", 0.1),
    )
    log(f"  ◀ {name} 第二阶段完成, 子结果: {sub_results}")
    return f"{name}-done"


async def test_mixed():
    """
    规则：gather 内部的任务可以继续内嵌 gather，行为是递归的。
    外层 gather 等待所有 mixed_task 完成，每个 mixed_task 内部又并发子任务。
    """
    log("=" * 50)
    log("测试 4: 混合 gather + 内嵌 gather")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    results = await asyncio.gather(
        mixed_task("M1"),
        mixed_task("M2"),
    )

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s")
    log(f"结果: {results}")
    log("")


# ============================================================
# 测试 5: Task 创建与回调
# ============================================================
async def test_task_callback():
    """
    规则：
    - create_task 立即调度协程，但不等待。
    - Task 在下一个事件循环 tick 或当前协程 await 时开始执行。
    - add_done_callback 在任务完成时同步回调（仍在事件循环中）。
    """
    log("=" * 50)
    log("测试 5: Task 创建与回调")
    log("=" * 50)

    callback_results = []

    def on_done(t):
        callback_results.append(t.result())
        log(f"  📋 callback: 任务完成，结果={t.result()}")

    log("主协程：创建 task1")
    t1 = asyncio.create_task(async_task("task1", 0.1))
    t1.add_done_callback(on_done)

    log("主协程：创建 task2")
    t2 = asyncio.create_task(async_task("task2", 0.2))
    t2.add_done_callback(on_done)

    log("主协程：做点别的事 (asyncio.sleep 0.05)")
    await asyncio.sleep(0.05)

    log("主协程：await task1")
    r1 = await t1
    log(f"主协程：await task1 返回 {r1}")

    log("主协程：await task2")
    r2 = await t2
    log(f"主协程：await task2 返回 {r2}")

    log(f"callback 收集的结果: {callback_results}")
    log("观察：callback 在任务完成时立即触发，可能在主协程 await 之前")
    log("")


# ============================================================
# 测试 6: 嵌套 gather
# ============================================================
async def test_nested_gather():
    """
    规则：gather 可以嵌套，行为等价于展平。
    外层 gather 等待内层 gather 全部完成。
    """
    log("=" * 50)
    log("测试 6: 嵌套 gather")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    results = await asyncio.gather(
        asyncio.gather(
            inner_task("a", 0.1),
            inner_task("b", 0.2),
        ),
        asyncio.gather(
            inner_task("c", 0.15),
            inner_task("d", 0.05),
        ),
    )

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s (期望 ≈ 0.2s)")
    log(f"结果: {results}")
    log("注意：嵌套 gather 返回嵌套列表结构")
    log("")


# ============================================================
# 测试 7: 异步生成器
# ============================================================
async def async_range(n, delay=0.05):
    """异步生成器"""
    for i in range(n):
        # await asyncio.sleep(delay)
        log(f"    async_range yield {i}")
        yield i


async def test_async_generator():
    """
    规则：async for 每次迭代 await __anext__，
    生成器内部 await 会 yield 控制权。
    """
    log("=" * 50)
    log("测试 7: 异步生成器")
    log("=" * 50)

    collected = []
    async for item in async_range(3, 0.05):
        log(f"  主循环收到: {item}")
        collected.append(item)

    log(f"收集结果: {collected}")
    log("")


# ============================================================
# 测试 8: 异步上下文管理器
# ============================================================
class AsyncTimer:
    """异步上下文管理器示例"""

    def __init__(self, name):
        self.name = name

    async def __aenter__(self):
        self.start = asyncio.get_event_loop().time()
        log(f"  ⏱ {self.name} 计时开始")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed = asyncio.get_event_loop().time() - self.start
        log(f"  ⏱ {self.name} 计时结束，耗时 {elapsed:.3f}s")
        return False  # 不吞掉异常


async def test_async_context():
    """
    规则：async with 的 __aenter__ 和 __aexit__ 都是协程，
    内部可以 await，行为和普通 async 函数一致。
    """
    log("=" * 50)
    log("测试 8: 异步上下文管理器")
    log("=" * 50)

    async with AsyncTimer("block1"):
        await async_task("inside-block1", 0.1)

    # 嵌套 async with
    async with AsyncTimer("outer"):
        async with AsyncTimer("inner"):
            await async_task("deep-inside", 0.05)

    log("")


# ============================================================
# 测试 9: 真实场景 - 模拟 agent 调用链
# ============================================================
async def search_tool(query, delay=0.1):
    """模拟搜索工具"""
    log(f"    🔍 搜索: {query}")
    await asyncio.sleep(delay)
    return f"搜索结果-{query}"


async def reasoning_agent(query):
    """模拟推理 agent：先搜索，再思考"""
    log(f"  🤖 推理 agent 开始: {query}")
    # 并发搜索多个来源
    results = await asyncio.gather(
        search_tool(f"{query}-来源1", 0.1),
        search_tool(f"{query}-来源2", 0.2),
    )
    log(f"  🤖 推理 agent 思考中...")
    await asyncio.sleep(0.1)  # 模拟思考
    return f"推理结果 based on {results}"


async def multi_agent_system():
    """模拟多 agent 系统"""
    log("🚀 多 agent 系统启动")
    # 同时启动多个 agent
    agent_results = await asyncio.gather(
        reasoning_agent("问题A"),
        reasoning_agent("问题B"),
    )
    log(f"🚀 所有 agent 完成: {agent_results}")
    return agent_results


async def test_real_world():
    """
    真实场景：多 agent 并发，每个 agent 内部又有并发工具调用。
    规则：所有层级的并发都是公平的，事件循环按就绪顺序调度。
    """
    log("=" * 50)
    log("测试 9: 真实场景 - 模拟 agent 调用链")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    await multi_agent_system()

    elapsed = asyncio.get_event_loop().time() - start
    log(f"总耗时: {elapsed:.3f}s")
    log("")


# ============================================================
# 测试 10: 同步 vs 异步 在事件循环中的行为
# ============================================================
def sync_blocking_task(name, delay=0.1):
    """同步阻塞任务（会阻塞事件循环！）"""
    log(f"  ⚠ {name} 同步阻塞开始")
    time.sleep(delay)  # 注意：这是 time.sleep，不是 asyncio.sleep
    log(f"  ⚠ {name} 同步阻塞结束")
    return f"{name}-done"


async def test_sync_vs_async():
    """
    规则：
    - time.sleep() 会阻塞整个事件循环，其他协程全部暂停。
    - asyncio.sleep() 只挂起当前协程，其他协程继续运行。
    - run_in_executor 可以把同步阻塞操作放到线程池，避免阻塞事件循环。
    """
    log("=" * 50)
    log("测试 10: 同步 vs 异步 在事件循环中的行为")
    log("=" * 50)
    start = asyncio.get_event_loop().time()

    # 错误示范：同步阻塞
    log("--- 子测试 10a: time.sleep 阻塞事件循环 ---")
    await asyncio.gather(
        async_task("async-A", 0.3),
        # 用 executor 包装同步函数，避免阻塞
        asyncio.get_event_loop().run_in_executor(None, sync_blocking_task, "sync-B", 0.3),
        async_task("async-C", 0.3),
    )

    elapsed = asyncio.get_event_loop().time() - start
    log(f"子测试 10a 总耗时: {elapsed:.3f}s (期望 ≈ 0.3s，因为 sync 被放到了线程池)")
    log("")

    # 正确示范：纯异步
    log("--- 子测试 10b: 纯 asyncio.sleep ---")
    start2 = asyncio.get_event_loop().time()
    await asyncio.gather(
        async_task("async-A", 0.3),
        async_task("async-B", 0.3),
        async_task("async-C", 0.3),
    )
    elapsed2 = asyncio.get_event_loop().time() - start2
    log(f"子测试 10b 总耗时: {elapsed2:.3f}s (期望 ≈ 0.3s)")
    log("")


# ============================================================
# 测试 11: 异常传播
# ============================================================
async def failing_task():
    """会失败的协程"""
    log("  ▶ failing_task 开始")
    await asyncio.sleep(0.05)
    raise ValueError("故意失败")


async def test_exception():
    """
    规则：
    - gather 中任一任务异常，默认 propagate，其他任务继续运行。
    - return_exceptions=True 时，异常作为结果返回，不传播。
    """
    log("=" * 50)
    log("测试 11: 异常传播")
    log("=" * 50)

    # 子测试 11a：默认行为
    log("--- 子测试 11a: 默认异常传播 ---")
    try:
        await asyncio.gather(
            async_task("ok1", 0.05),
            failing_task(),
            async_task("ok2", 0.05),
        )
    except ValueError as e:
        log(f"  ❌ 捕获异常: {e}")
    log("")

    # 子测试 11b：return_exceptions=True
    log("--- 子测试 11b: return_exceptions=True ---")
    results = await asyncio.gather(
        async_task("ok1", 0.05),
        failing_task(),
        async_task("ok2", 0.05),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log(f"  ❌ 结果中是异常: {r}")
        else:
            log(f"  ✅ 结果: {r}")
    log("")


# ============================================================
# 测试 12: asyncio.wait 与 FIRST_COMPLETED
# ============================================================
async def test_wait():
    """
    规则：
    - asyncio.wait 比 gather 更灵活。
    - FIRST_COMPLETED: 任一任务完成即返回。
    - ALL_COMPLETED: 全部完成（默认）。
    """
    log("=" * 50)
    log("测试 12: asyncio.wait 与 FIRST_COMPLETED")
    log("=" * 50)

    tasks = [
        asyncio.create_task(async_task("fast", 0.05)),
        asyncio.create_task(async_task("slow", 0.3)),
    ]

    # 等第一个完成
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    log(f"  已完成: {len(done)} 个, 未完成: {len(pending)} 个")

    # 取消未完成的任务
    for t in pending:
        t.cancel()
        log(f"  已取消一个 pending 任务")

    log("")


# ============================================================
# 主函数：运行所有测试
# ============================================================
async def main():
    log("🚀 asyncio 内嵌异步 & 组合运行规则测试")
    log("=" * 60)
    log("")

    await test_sequential()
    await test_gather()
    await test_nested()
    await test_mixed()
    await test_task_callback()
    await test_nested_gather()
    await test_async_generator()
    await test_async_context()
    await test_real_world()
    await test_sync_vs_async()
    await test_exception()
    await test_wait()

    log("=" * 60)
    log("✅ 所有测试完成！")
    log("")
    log("=" * 60)
    log("📋 核心规则总结：")
    log("=" * 60)
    log("""
1. await  = 挂起当前协程，等目标完成，期间事件循环可运行其他协程
2. gather = 并发启动多个协程，全部完成后返回，总耗时 = max(各任务)
3. 内嵌异步 = 外层协程内部 await 内层协程，内层期间外层挂起
4. create_task = 立即调度，不等待，下次 await/yield 时开始执行
5. 事件循环是协作式的：只有 await/yield 时才切换协程
6. time.sleep() 会阻塞整个事件循环，用 run_in_executor 或 asyncio.sleep 替代
7. 嵌套 gather 等价于展平，返回嵌套列表
8. async for / async with 本质也是 await，规则相同
9. gather 中异常默认传播，可用 return_exceptions=True 收集
10. asyncio.wait 比 gather 更灵活，支持 FIRST_COMPLETED 等策略
""")


if __name__ == "__main__":
    asyncio.run(main())
