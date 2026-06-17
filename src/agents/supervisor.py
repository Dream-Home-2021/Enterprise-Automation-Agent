"""
主管智能体 (Supervisor Agent)

职责：
  1. 解析多用户身份
  2. 消费全局状态，驱动情绪评估引擎
  3. 执行核心控制流路由（情绪网关）

情绪等级映射：
  - adoration : 综合分 >= 85 → 热情积极
  - normal    : 综合分 >= 60 → 正常协作
  - cold      : 综合分 >= 35 → 冷淡讽刺
  - strike    : 综合分 <  35 → 罢工拒绝工作
"""

import os
import json
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


# ---------------------------------------------------------------------------
# 角色配置矩阵
# ---------------------------------------------------------------------------
USER_PROFILES = {
    "main": {
        "role": "admin",
        "initial_metrics": {
            "politeness": 80,
            "trust": 80,
            "rationality": 80,
            "empathy": 80,
        },
        "tolerance": "high",      # 命令式语气扣分少，加分权重高
        "strike_threshold": 25,   # 高级豁免权：更低才罢工
    },
    "guest": {
        "role": "visitor",
        "initial_metrics": {
            "politeness": 50,
            "trust": 50,
            "rationality": 50,
            "empathy": 50,
        },
        "tolerance": "low",       # 不礼貌高倍率扣分
        "strike_threshold": 35,   # 一触即发
    },
}

# 情绪阈值
EMOTION_THRESHOLDS = {
    "adoration": 85,
    "normal": 60,
    "cold": 35,
    # below 35 → strike
}


# ---------------------------------------------------------------------------
# 情绪评估引擎
# ---------------------------------------------------------------------------

EMOTION_EVAL_PROMPT = """你是一个精确的用户行为量化评估引擎。

根据以下用户消息和当前评分，对四个维度（politeness, trust, rationality, empathy）进行增量调整。

当前评分:
{current_metrics}

用户角色: {role}
容错度: {tolerance}

用户最新消息:
{user_message}

请仅返回 JSON，格式如下（每个维度变化值在 -15 ~ +15 之间）:
{{
  "politeness_delta": <int>,
  "trust_delta": <int>,
  "rationality_delta": <int>,
  "empathy_delta": <int>,
  "reasoning": "<一句话评估理由>"
}}"""


async def evaluate_emotion(state: dict) -> dict:
    """
    情绪评估节点 — 调用 LLM 对四维评分做增量调整
    返回更新后的 state 片段
    """
    username = state.get("username", "guest")
    profile = USER_PROFILES.get(username, USER_PROFILES["guest"])

    # 获取最后一条用户消息
    messages = state.get("messages", [])
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    current_metrics = state.get("user_metrics", profile["initial_metrics"])

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.1,
    )

    prompt = EMOTION_EVAL_PROMPT.format(
        current_metrics=json.dumps(current_metrics, ensure_ascii=False),
        role=profile["role"],
        tolerance=profile["tolerance"],
        user_message=last_user_msg,
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        deltas = json.loads(response.content)
    except (json.JSONDecodeError, Exception):
        # 容错：JSON 解析失败时不做调整
        deltas = {
            "politeness_delta": 0,
            "trust_delta": 0,
            "rationality_delta": 0,
            "empathy_delta": 0,
            "reasoning": "评估失败，保持当前评分",
        }

    # 应用增量，clamp 到 [0, 100]
    new_metrics = {}
    for key in ["politeness", "trust", "rationality", "empathy"]:
        delta_key = f"{key}_delta"
        delta = deltas.get(delta_key, 0)

        # 角色韧性调制
        if profile["tolerance"] == "high":
            if delta < 0:
                delta = int(delta * 0.5)  # 高韧性：扣分减半
            elif delta > 0:
                delta = int(delta * 1.3)  # 高韧性：加分加成
        elif profile["tolerance"] == "low":
            if delta < 0:
                delta = int(delta * 2.0)  # 低韧性：扣分翻倍

        new_val = current_metrics.get(key, 50) + delta
        new_metrics[key] = max(0, min(100, new_val))

    # 计算综合分 → 映射情绪
    avg_score = sum(new_metrics.values()) / len(new_metrics)
    strike_threshold = profile["strike_threshold"]

    if avg_score >= EMOTION_THRESHOLDS["adoration"]:
        emotion = "adoration"
    elif avg_score >= EMOTION_THRESHOLDS["normal"]:
        emotion = "normal"
    elif avg_score >= strike_threshold:
        emotion = "cold"
    else:
        emotion = "strike"

    print(f"[emotion] {username}: avg={avg_score:.1f} → {emotion} | {deltas.get('reasoning', '')}")

    return {
        "user_metrics": new_metrics,
        "current_emotion": emotion,
    }


# ---------------------------------------------------------------------------
# 路由决策
# ---------------------------------------------------------------------------

def route_by_emotion(state: dict) -> str:
    """
    情绪网关路由函数 — 根据 current_emotion 决定下游节点

    Returns:
        'data_agent'    — 情绪正常以上，允许数据分析
        'chat_defender' — 冷淡或罢工，切换防御性陪聊
    """
    emotion = state.get("current_emotion", "normal")

    if emotion in ("adoration", "normal"):
        return "data_agent"
    else:  # cold, strike
        return "chat_defender"


async def supervisor_node(state: dict) -> dict:
    """
    Supervisor 主节点 — 串联：身份鉴权 → 情绪评估 → 上下文注入
    """
    username = state.get("username", "guest")
    profile = USER_PROFILES.get(username, USER_PROFILES["guest"])

    # 首次会话初始化指标
    if not state.get("user_metrics") or all(v == 50 for v in state["user_metrics"].values()):
        initial = profile["initial_metrics"].copy()
        state_updates = {"user_metrics": initial}
    else:
        state_updates = {}

    # 注入角色到状态
    state_updates["role"] = profile["role"]

    # 执行情绪评估
    emotion_updates = await evaluate_emotion(state)
    state_updates.update(emotion_updates)

    return state_updates
