# -*- coding: utf-8 -*-
"""测试 create_ticket — 验证 group_id / customer_id 正确转换。"""
import asyncio
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from agent.api import zammad_client


async def test_create_without_customer():
    """不传 customer 创建工单。"""
    print("=== Test 1: 不传 customer ===")
    data = await zammad_client.create_ticket(
        title="[测试] 无客户工单",
        body="验证不传 customer 时不会报错。",
    )
    print(f"✅ 成功! 工单 ID: {data.get('id')}, 标题: {data.get('title')}")
    return data.get("id")


async def test_create_with_customer():
    """传 customer 邮箱创建工单 — 内部会转为 customer_id。"""
    print("\n=== Test 2: 传 customer 邮箱 ===")
    data = await zammad_client.create_ticket(
        title="[测试] 有客户工单",
        body="验证 customer 邮箱能正确转为 customer_id。",
        customer="fanglongsheng1106@gmail.com",
    )
    print(f"✅ 成功! 工单 ID: {data.get('id')}, 标题: {data.get('title')}")
    return data.get("id")


async def test_create_with_empty_string_customer():
    """传空字符串 customer — 应视为 None。"""
    print("\n=== Test 3: customer 为空字符串 ===")
    data = await zammad_client.create_ticket(
        title="[测试] 空字符串客户",
        body="空字符串 customer 应被当作 None 处理。",
        customer="",
    )
    print(f"✅ 成功! 工单 ID: {data.get('id')}, 标题: {data.get('title')}")
    return data.get("id")


async def main():
    await test_create_without_customer()
    await test_create_with_customer()
    await test_create_with_empty_string_customer()
    print("\n🎉 全部测试通过!")


if __name__ == "__main__":
    asyncio.run(main())
