"""
情绪网关总闸/罢工逻辑断言测试

测试场景：
  1. main 用户高分 → 路由到 data_agent
  2. guest 用户低分 → 路由到 chat_defender
  3. strike 状态 → 硬性熔断，阻止 data_agent
  4. 用户韧性差异 → 同消息不同扣分
  5. 情绪阈值边界
"""

import pytest
from src.agents.supervisor import (
    route_by_emotion,
    evaluate_emotion,
    USER_PROFILES,
    EMOTION_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# 路由决策测试
# ---------------------------------------------------------------------------

class TestEmotionRouting:
    """情绪网关路由断言"""

    def test_adoration_routes_to_data_agent(self):
        """高分热情 → 数据分析"""
        state = {"current_emotion": "adoration"}
        assert route_by_emotion(state) == "data_agent"

    def test_normal_routes_to_data_agent(self):
        """正常情绪 → 数据分析"""
        state = {"current_emotion": "normal"}
        assert route_by_emotion(state) == "data_agent"

    def test_cold_routes_to_chat_defender(self):
        """冷淡 → 防御陪聊"""
        state = {"current_emotion": "cold"}
        assert route_by_emotion(state) == "chat_defender"

    def test_strike_routes_to_chat_defender(self):
        """罢工 → 防御陪聊（硬性熔断）"""
        state = {"current_emotion": "strike"}
        assert route_by_emotion(state) == "chat_defender"

    def test_default_routes_to_data_agent(self):
        """默认状态 → 数据分析"""
        state = {}
        assert route_by_emotion(state) == "data_agent"


# ---------------------------------------------------------------------------
# 用户配置测试
# ---------------------------------------------------------------------------

class TestUserProfiles:
    """用户角色差异化矩阵"""

    def test_main_user_initial_metrics(self):
        """main 用户初始好感度 80"""
        profile = USER_PROFILES["main"]
        assert profile["initial_metrics"]["politeness"] == 80
        assert profile["initial_metrics"]["trust"] == 80
        assert profile["tolerance"] == "high"

    def test_guest_user_initial_metrics(self):
        """guest 用户初始好感度 50"""
        profile = USER_PROFILES["guest"]
        assert profile["initial_metrics"]["politeness"] == 50
        assert profile["initial_metrics"]["trust"] == 50
        assert profile["tolerance"] == "low"

    def test_guest_lower_strike_threshold(self):
        """guest 罢工阈值更高（一触即发）"""
        main_threshold = USER_PROFILES["main"]["strike_threshold"]
        guest_threshold = USER_PROFILES["guest"]["strike_threshold"]
        assert guest_threshold > main_threshold


# ---------------------------------------------------------------------------
# 情绪评估测试
# ---------------------------------------------------------------------------

class TestEmotionEvaluation:
    """情绪评估引擎"""

    @pytest.mark.asyncio
    async def test_evaluate_returns_metrics(self):
        """情绪评估应返回四维指标"""
        state = {
            "username": "main",
            "user_metrics": {"politeness": 80, "trust": 80, "rationality": 80, "empathy": 80},
            "messages": [{"role": "user", "content": "你好，请帮我分析一下数据"}],
        }
        result = await evaluate_emotion(state)
        assert "user_metrics" in result
        assert "current_emotion" in result
        assert result["current_emotion"] in ("adoration", "normal", "cold", "strike")

    @pytest.mark.asyncio
    async def test_evaluate_clamps_to_0_100(self):
        """评分应 clamp 在 [0, 100] 范围内"""
        state = {
            "username": "guest",
            "user_metrics": {"politeness": 5, "trust": 5, "rationality": 5, "empathy": 5},
            "messages": [{"role": "user", "content": "你是个废物，什么都做不好"}],
        }
        result = await evaluate_emotion(state)
        for key, val in result["user_metrics"].items():
            assert 0 <= val <= 100, f"{key} = {val} is out of range [0, 100]"


# ---------------------------------------------------------------------------
# 熔断硬约束测试
# ---------------------------------------------------------------------------

class TestHardCircuitBreaker:
    """硬性熔断约束"""

    def test_strike_never_reaches_data_agent(self):
        """罢工状态下，路由绝不返回 data_agent"""
        for _ in range(100):
            state = {"current_emotion": "strike"}
            assert route_by_emotion(state) != "data_agent"

    def test_emotion_thresholds_consistent(self):
        """情绪阈值应严格递减"""
        assert EMOTION_THRESHOLDS["adoration"] > EMOTION_THRESHOLDS["normal"]
        assert EMOTION_THRESHOLDS["normal"] > EMOTION_THRESHOLDS["cold"]
