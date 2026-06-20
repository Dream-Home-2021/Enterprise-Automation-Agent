# -*- coding: utf-8 -*-
"""查 Zammad 用户列表，找 guest 或默认用户。"""
import asyncio
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

import httpx

ZAMMAD_URL = os.getenv("ZAMMAD_URL", "http://localhost:8080")
TOKEN = os.getenv("ZAMMAD_API_TOKEN", "")


async def test():
    headers = {
        "Authorization": f"Token token={TOKEN}",
        "Content-Type": "application/json",
    }
    client = httpx.AsyncClient(mounts={}, timeout=30)

    # 查所有用户
    print("=== All Users ===")
    r = await client.get(f"{ZAMMAD_URL}/api/v1/users", headers=headers)
    if r.status_code == 200:
        for u in r.json():
            print(f"  id={u['id']}, email={u.get('email')!r}, firstname={u.get('firstname')!r}, lastname={u.get('lastname')!r}, active={u.get('active')}")
    else:
        print(f"  Error {r.status_code}: {r.text[:200]}")

    # 测试: customer_id=1 是什么
    print("\n=== Test create with customer_id=1 ===")
    r = await client.post(
        f"{ZAMMAD_URL}/api/v1/tickets",
        headers=headers,
        json={
            "title": "[测试] guest user",
            "group_id": 1,
            "customer_id": 1,
            "article": {
                "subject": "[测试] guest user",
                "body": "测试内容",
                "type": "web",
                "internal": False,
            },
        },
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"✅ 成功! id={r.json().get('id')}")
    else:
        print(f"Body: {r.text[:500]}")


asyncio.run(test())
