"""End-to-end test: Supervisor + Chat Agent + Zammad API."""
import asyncio, os, sys, io

# Fix Windows GBK console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from agent.supervisor.graph import get_supervisor


async def test():
    supervisor = get_supervisor()

    tests = [
        ("greeting", "你好"),
        ("list tickets", "查一下工单列表"),
        ("search user", "搜索用户 admin"),
        ("get user", "查看用户 3 的详情"),
    ]

    for label, msg in tests:
        print(f"=== {label}: {msg} ===")
        result = await supervisor.ainvoke(
            {"messages": [{"role": "user", "content": msg}]}
        )
        text = result["messages"][-1].content
        print(f"Response: {text}")
        print()


asyncio.run(test())
