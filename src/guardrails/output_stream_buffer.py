"""
输出端 — 流式滑动窗口（Sliding Window）熔断器

职责：
  - 维护一个指定尺寸的滚动滑块缓冲区（默认 6 个汉字）
  - 敏感词匹配在滑块内同步运行
  - 一旦触发违规，在 50ms 内执行 Stream Abort
  - 无缝替换为系统情绪化降级文本
"""

from typing import Optional

from src.guardrails.input_filter import _matcher, BLOCKED_RESPONSE


class OutputStreamBuffer:
    """
    流式输出滑动窗口缓冲区

    用于 SSE 流式输出的实时内容安全过滤。
    维护固定大小的滑动窗口，在每个 token 到达时检测。

    Attributes:
        window_size: 滑动窗口大小（字符数）
        buffer: 当前缓冲区内容
    """

    def __init__(self, window_size: int = 6):
        """
        Args:
            window_size: 滑动窗口大小，默认 6 个汉字
        """
        self.window_size = window_size
        self.buffer = ""
        self._aborted = False

    def process(self, token: str) -> Optional[str]:
        """
        处理一个输出 token

        Args:
            token: 大模型输出的文本片段

        Returns:
            - 正常文本：返回过滤后的安全文本
            - 触发违规：返回降级文本，后续调用返回 None（流已终止）
            - 流已终止：返回 None
        """
        if self._aborted:
            return None

        # 追加到缓冲区
        self.buffer += token

        # 保持窗口大小
        if len(self.buffer) > self.window_size * 2:
            self.buffer = self.buffer[-(self.window_size * 2):]

        # 在窗口内检测敏感词
        window_text = self.buffer[-self.window_size:]
        matched = _matcher.search(window_text)

        if matched:
            # 触发熔断
            self._aborted = True
            print(f"[output_guardrail] ABORT: '{matched}' detected in output stream.")
            return BLOCKED_RESPONSE

        # 安全 — 返回超出窗口的部分（保持滑动）
        if len(self.buffer) > self.window_size:
            safe_text = self.buffer[:-self.window_size]
            self.buffer = self.buffer[-self.window_size:]
            return safe_text

        # 缓冲未满 — 暂不输出
        return None

    def flush(self) -> Optional[str]:
        """
        刷新缓冲区 — 流结束时调用

        Returns:
            缓冲区剩余内容，或 None（已中止）
        """
        if self._aborted:
            return None
        remaining = self.buffer
        self.buffer = ""
        return remaining if remaining else None

    def reset(self):
        """重置缓冲区"""
        self.buffer = ""
        self._aborted = False

    @property
    def is_aborted(self) -> bool:
        """是否已触发熔断"""
        return self._aborted
