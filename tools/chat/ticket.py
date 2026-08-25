"""
工单 CRUD 工具

提供给 Chat Agent 的工单操作工具，使用 @tool 装饰器。
"""

import asyncio

from langchain.tools import tool

from agent.api import zammad_client
from utils.log import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """在同步函数中安全执行异步协程。"""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(coro)


@tool
def list_tickets(query: str = "") -> str:
    """列出或搜索工单。当 query 为空时返回所有工单列表；传入关键词时按关键词搜索工单。
    返回工单编号、标题、状态。"""
    if query.strip():
        results = _run_async(zammad_client.search_tickets(query))
    else:
        results = _run_async(zammad_client.list_tickets())

    if not results:
        return "没有找到工单。"

    lines = [f"共 {len(results)} 个工单："]
    for t in results:
        tid = t.get("id", "?")
        title = t.get("title", "无标题")
        state = t.get("state", "未知")
        lines.append(f"- #{tid} {title}（{state}）")
    return "\n".join(lines)


@tool
def get_ticket(ticket_id: int) -> str:
    """根据工单 ID 查看单个工单的详细信息。
    包括标题、状态、优先级、客户、负责客服等。"""
    t = _run_async(zammad_client.get_ticket(ticket_id))
    return (
        f"工单 #{t.get('id')}\n"
        f"标题：{t.get('title', '无标题')}\n"
        f"状态：{t.get('state', '未知')}\n"
        f"优先级：{t.get('priority', '未知')}\n"
        f"客户 ID：{t.get('customer_id', '未知')}\n"
        f"负责人 ID：{t.get('owner_id', '未知')}\n"
        f"文章数：{t.get('article_count', 0)}"
    )


@tool
def create_ticket(title: str, body: str, customer_email: str = "") -> str:
    """创建一个新工单。需要提供标题(title)、内容(body)和客户邮箱(customer_email)。
    客户邮箱可选，不传时使用默认客户。"""
    data = _run_async(zammad_client.create_ticket(
        title=title,
        body=body,
        customer=customer_email if customer_email else None,
    ))
    return f"工单已创建：#{data.get('id')} - {data.get('title')}"


@tool
def update_ticket(ticket_id: int, state: str = "", priority: str = "") -> str:
    """更新工单信息。可修改的状态(state)：new, open, pending reminder, pending close, closed。
    可修改的优先级(priority)：1 low, 2 normal, 3 high。"""
    fields = {}
    if state:
        fields["state"] = state
    if priority:
        fields["priority"] = priority

    if not fields:
        return "请指定要修改的字段（state 或 priority）。"

    _run_async(zammad_client.update_ticket(ticket_id, **fields))
    return f"工单 #{ticket_id} 已更新。"