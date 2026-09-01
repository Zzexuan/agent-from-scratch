"""上下文窗口预算：把窗口当 RAM 做配额管理（D2 手搓规格）。

- `ContextWindow(budget)`：budget = 模型窗口 × 安全系数（默认 0.75），
  即"系统指令 + 工具 schema + 历史 + 输出余量"四个份额的总上限。
- `check()` 返回 `ContextReport`：使用率与是否该压缩（D3 压缩器只认 should_compress）。
- 使用率达到 75% 就预警：75% 触发、压到 37.5%（≈ 一半），对齐业界实践。
"""

from pydantic import BaseModel, Field

from afg.context.counter import TokenCounter
from afg.context.messages import Message

# 压缩触发阈值：使用率达到该比例时告警 / 触发压缩（D3 复用同一常量）
COMPRESS_THRESHOLD = 0.75


class ContextReport(BaseModel):
    """一次 check 的结果：用量、预算、使用率、是否触发压缩。"""

    total_tokens: int = 0
    budget: int = 0
    usage_ratio: float = Field(default=0.0, ge=0.0)
    should_compress: bool = False


class ContextWindow:
    """上下文预算窗口。两种构造：直接给 budget，或由模型窗口 × 安全系数推导。"""

    def __init__(self, budget: int) -> None:
        if budget <= 0:
            raise ValueError(f"budget 必须为正整数，收到 {budget}")
        self.budget = budget

    @classmethod
    def from_model(cls, window_tokens: int, safety_ratio: float = 0.75) -> "ContextWindow":
        """budget = 模型窗口 × 安全系数（主文档契约）。"""
        return cls(int(window_tokens * safety_ratio))

    def check(self, messages: list[Message], counter: TokenCounter) -> ContextReport:
        """统计 messages 总量并返回使用率报告；should_compress 由 75% 阈值决定。"""
        total = counter.count_messages(messages)
        usage = total / self.budget
        return ContextReport(
            total_tokens=total,
            budget=self.budget,
            usage_ratio=usage,
            should_compress=usage >= COMPRESS_THRESHOLD,
        )