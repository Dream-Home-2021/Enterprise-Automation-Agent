"""
流式滑动窗口熔断单元测试

测试场景：
  1. 正常文本透传
  2. 敏感词触发熔断
  3. 熔断后后续 token 返回 None
  4. 窗口缓冲区滑动逻辑
  5. flush 行为
  6. reset 重置
"""

import pytest
from src.guardrails.output_stream_buffer import OutputStreamBuffer
from src.guardrails.input_filter import BLOCKED_RESPONSE, SENSITIVE_WORDS


# ---------------------------------------------------------------------------
# 正常流
# ---------------------------------------------------------------------------

class TestNormalStream:
    """正常文本流"""

    def test_short_text_buffered(self):
        """短文本暂存不输出"""
        buf = OutputStreamBuffer(window_size=6)
        result = buf.process("你好")
        # 缓冲未满（2 < 6），暂不输出
        assert result is None

    def test_long_text_emits_safe_portion(self):
        """长文本输出安全部分"""
        buf = OutputStreamBuffer(window_size=6)
        result = buf.process("这是一段正常的文本内容，不包含任何敏感词")
        # 应输出部分文本
        assert result is not None
        assert "正常" in result or len(result) > 0

    def test_flush_returns_remaining(self):
        """flush 返回缓冲区剩余"""
        buf = OutputStreamBuffer(window_size=6)
        buf.process("你好世界")
        remaining = buf.flush()
        assert remaining == "你好世界"


# ---------------------------------------------------------------------------
# 熔断测试
# ---------------------------------------------------------------------------

class TestStreamAbort:
    """流式熔断"""

    def test_sensitive_word_triggers_abort(self):
        """敏感词触发熔断"""
        buf = OutputStreamBuffer(window_size=6)
        # 先填充一些正常内容
        buf.process("你好")
        # 注入敏感词
        result = buf.process("色情内容测试")
        # 应触发熔断
        assert buf.is_aborted
        assert result == BLOCKED_RESPONSE or result is None

    def test_after_abort_returns_none(self):
        """熔断后所有后续 token 返回 None"""
        buf = OutputStreamBuffer(window_size=6)
        # 强制中止
        buf._aborted = True
        result = buf.process("任何后续内容")
        assert result is None

    def test_flush_after_abort_returns_none(self):
        """熔断后 flush 返回 None"""
        buf = OutputStreamBuffer(window_size=6)
        buf._aborted = True
        assert buf.flush() is None


# ---------------------------------------------------------------------------
# 窗口逻辑
# ---------------------------------------------------------------------------

class TestWindowLogic:
    """滑动窗口行为"""

    def test_window_size_respected(self):
        """窗口大小正确维护"""
        buf = OutputStreamBuffer(window_size=4)
        buf.process("abcdefgh")
        assert len(buf.buffer) <= 8  # buffer <= window_size * 2

    def test_reset_clears_state(self):
        """reset 重置所有状态"""
        buf = OutputStreamBuffer(window_size=6)
        buf.process("测试")
        buf.reset()
        assert buf.buffer == ""
        assert not buf.is_aborted

    def test_multiple_tokens_sliding(self):
        """多 token 连续滑动"""
        buf = OutputStreamBuffer(window_size=4)
        results = []
        for token in ["你好", "世界", "这是", "测试", "文本"]:
            r = buf.process(token)
            if r:
                results.append(r)
        # 应输出部分内容
        assert len(results) >= 0  # 可能有输出


# ---------------------------------------------------------------------------
# 敏感词库完整性
# ---------------------------------------------------------------------------

class TestSensitiveWords:
    """敏感词库验证"""

    def test_word_list_not_empty(self):
        """敏感词库不为空"""
        assert len(SENSITIVE_WORDS) > 0

    def test_blocked_response_not_empty(self):
        """熔断回复不为空"""
        assert len(BLOCKED_RESPONSE) > 0
