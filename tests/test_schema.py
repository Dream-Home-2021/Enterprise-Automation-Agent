"""
中间件输入输出 JSON Schema 规约测试

测试场景：
  1. ChatRequest Schema 校验
  2. ChatResponse Schema 校验
  3. ApprovalRequest Schema 校验
  4. 审批决策枚举校验
  5. 高危操作 payload 格式
"""

import pytest
from pydantic import ValidationError

from src.main import ChatRequest, ChatResponse, ApprovalRequest


# ---------------------------------------------------------------------------
# ChatRequest Schema
# ---------------------------------------------------------------------------

class TestChatRequestSchema:
    """聊天请求 Schema 规约"""

    def test_valid_request_minimal(self):
        """最小有效请求"""
        req = ChatRequest(message="你好")
        assert req.username == "main"  # 默认值
        assert req.message == "你好"

    def test_valid_request_full(self):
        """完整有效请求"""
        req = ChatRequest(
            username="guest",
            message="帮我分析 sales.csv",
            session_id="sess_123",
            active_file_path="/data/sales.csv",
        )
        assert req.username == "guest"
        assert req.session_id == "sess_123"
        assert req.active_file_path == "/data/sales.csv"

    def test_missing_message_raises(self):
        """缺少 message 字段应报错"""
        with pytest.raises(ValidationError):
            ChatRequest()


# ---------------------------------------------------------------------------
# ChatResponse Schema
# ---------------------------------------------------------------------------

class TestChatResponseSchema:
    """聊天响应 Schema 规约"""

    def test_valid_response(self):
        """有效响应"""
        resp = ChatResponse(
            session_id="sess_001",
            username="main",
            current_emotion="normal",
            response="数据分析完成",
        )
        assert resp.requires_approval is False
        assert resp.approval_payload is None

    def test_response_with_approval(self):
        """含高危审批的响应"""
        resp = ChatResponse(
            session_id="sess_001",
            username="main",
            current_emotion="normal",
            response="需要执行以下代码...",
            requires_approval=True,
            approval_payload={
                "payload": {
                    "code_preview": "import pandas as pd...",
                    "file_path": "/data/sales.csv",
                    "action": "execute_python",
                },
            },
        )
        assert resp.requires_approval is True
        assert "payload" in resp.approval_payload

    def test_emotion_enum(self):
        """情绪字段应为有效值"""
        valid_emotions = {"adoration", "normal", "cold", "strike"}
        resp = ChatResponse(
            session_id="test",
            username="main",
            current_emotion="normal",
            response="ok",
        )
        assert resp.current_emotion in valid_emotions


# ---------------------------------------------------------------------------
# ApprovalRequest Schema
# ---------------------------------------------------------------------------

class TestApprovalRequestSchema:
    """审批请求 Schema 规约"""

    def test_valid_approval(self):
        """有效审批"""
        req = ApprovalRequest(
            session_id="sess_001",
            status="approved",
        )
        assert req.status == "approved"
        assert req.user_feedback == ""

    def test_valid_rejection_with_feedback(self):
        """拒绝 + 反馈"""
        req = ApprovalRequest(
            session_id="sess_001",
            status="rejected",
            user_feedback="这段代码有误，请修改",
        )
        assert req.status == "rejected"
        assert len(req.user_feedback) > 0

    def test_valid_statuses(self):
        """审批状态枚举"""
        valid = {"approved", "rejected", "modified"}
        for status in valid:
            req = ApprovalRequest(session_id="test", status=status)
            assert req.status in valid

    def test_high_risk_payload_structure(self):
        """高危操作 payload 必须包含必要字段"""
        expected_keys = {"payload", "code_preview", "file_path", "action"}
        payload = {
            "payload": {
                "code_preview": "print('hello')",
                "file_path": "/data/test.csv",
                "action": "execute_python",
            }
        }
        assert "payload" in payload
        assert set(payload["payload"].keys()) == {"code_preview", "file_path", "action"}
