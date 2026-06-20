"""
Zammad API HTTP 客户端

封装对 Zammad REST API 的 HTTP 请求，使用 httpx.AsyncClient。
所有方法返回原始 JSON 字典。

Gradio UI → service.py (Supervisor Graph)
                              │
                    call_chat_agent tool
                              │
                    Chat Agent Graph
                         │         │
                   list_tickets  search_users
                   get_ticket    get_user
                   create_ticket
                   update_ticket
                         │
                    Zammad API (localhost:8080)
                              │
                    ✅ 全权限 token — 全部 200
"""

import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from utils.log import get_logger

load_dotenv()

logger = get_logger(__name__)

_BASE_URL = os.getenv("ZAMMAD_URL", "http://localhost:8080") + "/api/v1"
_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "")

# 共享客户端：空 mounts 彻底禁用代理（无视 HTTP_PROXY 环境变量）
_client = httpx.AsyncClient(mounts={}, timeout=30)


def _headers() -> dict:
    return {
        "Authorization": f"Token token={_TOKEN}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    return f"{_BASE_URL}{path}"


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

async def list_tickets(page: int = 1, per_page: int = 5) -> list[dict]:
    """获取工单列表，返回工单字典列表。"""
    # get请求方式\api组装\请求头\请求参数
    resp = await _client.get(
        _url("/tickets"),
        headers=_headers(),
        params={"page": page, "per_page": per_page},
    )
    # HTTP 响应状态码检测，失败就抛异常，不会继续解析
    resp.raise_for_status()
    # 成功才解析 JSON
    data = resp.json()
    logger.info("list_tickets: got %d tickets", len(data))
    return data


async def search_tickets(query: str) -> list[dict]:
    """按关键词搜索工单。"""
    resp = await _client.get(
        _url("/tickets/search"),
        headers=_headers(),
        params={"query": query},
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info('search_tickets("%s"): got %d results', query, len(data))
    return data


async def get_ticket(ticket_id: int) -> dict:
    """获取单个工单详情。"""
    resp = await _client.get(
        _url(f"/tickets/{ticket_id}"),
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("get_ticket(%d): %s", ticket_id, data.get("title", ""))
    return data


async def _group_id(name: str) -> int:
    """按名称查组 ID（如 'Users' → 1）。"""
    resp = await _client.get(_url("/groups"), headers=_headers())
    resp.raise_for_status()
    for g in resp.json():
        if g["name"] == name:
            return g["id"]
    raise ValueError(f"Group not found: {name!r}")


async def _customer_id(email: str) -> int:
    """按邮箱查用户 ID。"""
    resp = await _client.get(
        _url("/users/search"), headers=_headers(), params={"query": email}
    )
    resp.raise_for_status()
    results = resp.json()
    if results:
        return results[0]["id"]
    raise ValueError(f"User not found: {email!r}")


async def create_ticket(
    title: str,
    body: str,
    customer: Optional[str] = None,
    group: str = "Users",
) -> dict:
    """创建工单，同时创建首条文章。

    Args:
        title: 工单标题。
        body: 首条消息正文。
        customer: 客户邮箱（可选），会转为 customer_id；不传则使用 guest user (id=1)。
        group: 组名（默认 'Users'），会转为 group_id 传给 Zammad。
    """
    payload: dict[str, Any] = {
        "title": title,
        "group_id": await _group_id(group),
        "customer_id": await _customer_id(customer) if customer else 1,
        "article": {
            "subject": title,
            "body": body,
            "type": "web",
            "internal": False,
        },
    }

    resp = await _client.post(
        _url("/tickets"),
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("create_ticket: id=%s title=%s", data.get("id"), title)
    return data


async def update_ticket(ticket_id: int, **fields) -> dict:
    """更新工单字段（state / priority / group / title / body / type / internal等）。"""
    resp = await _client.put(
        _url(f"/tickets/{ticket_id}"),
        headers=_headers(),
        json=fields,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("update_ticket(%d): updated", ticket_id)
    return data


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def search_users(query: str) -> list[dict]:
    """按名称 / 邮箱搜索用户。"""
    resp = await _client.get(
        _url("/users/search"),
        headers=_headers(),
        params={"query": query},
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info('search_users("%s"): got %d results', query, len(data))
    return data


async def get_user(user_id: int) -> dict:
    """获取单个用户详情。"""
    resp = await _client.get(
        _url(f"/users/{user_id}"),
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("get_user(%d): %s %s", user_id, data.get("firstname"), data.get("lastname"))
    return data


async def get_current_user() -> dict:
    """获取当前认证用户信息。"""
    resp = await _client.get(
        _url("/users/me"),
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("get_current_user: %s %s", data.get("firstname"), data.get("lastname"))
    return data