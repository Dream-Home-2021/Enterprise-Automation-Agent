"""
用户搜索工具

提供给 Chat Agent 的用户查询工具，使用 @tool 装饰器。
"""

from langchain.tools import tool

from agent.api import zammad_client
from utils.log import get_logger

logger = get_logger(__name__)


@tool
async def search_users(query: str) -> str:
    """搜索 Zammad 系统中的用户，按姓名或邮箱搜索。返回匹配用户的基本信息。"""
    results = await zammad_client.search_users(query)

    if not results:
        return f"没有找到匹配「{query}」的用户。"

    lines = [f"找到 {len(results)} 个用户："]
    for u in results:
        uid = u.get("id", "?")
        first = u.get("firstname", "")
        last = u.get("lastname", "")
        email = u.get("email", "")
        role = "Agent" if u.get("role_ids") and 2 in u.get("role_ids", []) else "Customer"
        lines.append(f"- #{uid} {first} {last} <{email}> ({role})")
    return "\n".join(lines)


@tool
async def get_user(user_id: int) -> str:
    """根据用户 ID 获取用户详细信息。包括姓名、邮箱、角色、组织等。"""
    u = await zammad_client.get_user(user_id)
    return (
        f"用户 #{u.get('id')}\n"
        f"姓名：{u.get('firstname', '')} {u.get('lastname', '')}\n"
        f"邮箱：{u.get('email', '')}\n"
        f"角色 IDs：{u.get('role_ids', [])}\n"
        f"组织 ID：{u.get('organization_id', '无')}\n"
        f"活跃：{'是' if u.get('active') else '否'}"
    )