"""
全局上下文 GlobalAgentState — TypedDict 规范

贯穿 LangGraph 生命周期的状态机定义，所有节点共享此 Schema。
"""

from typing import TypedDict, NotRequired


class GlobalAgentState(TypedDict):
    """
    LangGraph 全局状态机 Schema

    Attributes:
        username: 用户唯一标识 ('main' | 'guest')
        role: 权限标签 ('admin' | 'visitor')
        user_metrics: 四维量化评分 (politeness, trust, rationality, empathy)
        current_emotion: 激活情绪 ('adoration', 'normal', 'cold', 'strike')
        long_term_insights: RAG 召回的历史观察日记列表
        messages: 经修剪的短期滚动聊天记录
        active_file_path: 当前操作的文件路径
        last_code_generated: MCP 沙箱拟执行或已执行的 Python 代码
        requires_approval: 高危操作挂起拦截标志
        approval_result: 中间件返回的审批决策
    """

    # ---- 身份鉴权 ----
    username: str
    role: str  # 'admin' | 'visitor'

    # ---- 情绪引擎 ----
    user_metrics: dict  # {politeness: float, trust: float, rationality: float, empathy: float}
    current_emotion: str  # 'adoration' | 'normal' | 'cold' | 'strike'

    # ---- 记忆 ----
    long_term_insights: list  # RAG 召回的观察日记
    messages: list  # 短期滚动消息 [{role, content}]

    # ---- 数据操作 ----
    active_file_path: str
    last_code_generated: str

    # ---- Human-in-the-Loop 审批 ----
    requires_approval: bool
    approval_result: dict
