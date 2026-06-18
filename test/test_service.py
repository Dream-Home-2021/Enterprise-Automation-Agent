# -*- coding: utf-8 -*-
"""
测试 make_generate_response() 的函数内部数据流转。

核心思路：开启 debug=True，函数内部每个关键变量变化都会 print 出来。
我们只需要准备输入、驱动生成器遍历所有 yield，就能完整看到：
  输入 → 阶段1(输入处理) → 阶段2(逐token流式) → 阶段3(收尾) → 输出

运行方式:
    cd d:\GameDownload\My-agent
    python test/test_service.py
"""

import asyncio
from agent.service import make_generate_response


async def main():
    # ── 准备输入 ──────────────────────────────────────────────────
    message = "你好，请用一句话介绍你自己"
    history = []

    # ── 创建生成器（开启 debug）───────────────────────────────────
    # debug=True → 函数内部所有关键变量变化都会打印
    generate_response = make_generate_response(debug=True)

    # ── 驱动生成器，遍历所有 yield ────────────────────────────────
    # 每次 yield 对应一次 Gradio 界面刷新
    step = 0
    async for clear_text, updated_history in generate_response(message, history):
        step += 1
        # yield 本身的返回值也可以打印（debug 内部已打印更多细节）
        print(f"[yield #{step}] clear_text={clear_text!r}, history 条数={len(updated_history)}")

    # ── 最终输出 ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[最终结果] history 共 {len(history)} 条消息:")
    for i, msg in enumerate(history):
        print(f"  [{i}] role={msg['role']!r}, content={msg['content']!r}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
