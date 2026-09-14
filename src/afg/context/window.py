from pydantic import BaseModel, Field

COMPRESS_THRESHOLD = 0.75


class ContextReport(BaseModel):
    total_tokens: int = 0
    budget: int = 0
    usage_ratio: float = Field(default=0.0, ge=0.0)
    should_compress: bool = False


class ContextWindow:
    def __init__(self, budget):
        if budget <= 0:
            raise ValueError(f"budget 必须为正整数，收到 {budget}")
        self.budget = budget

    @classmethod
    def from_model(cls, window_tokens, safety_ratio=0.75):
        return cls(int(window_tokens * safety_ratio))

    def check(self, messages, counter):
        total = counter.count_messages(messages)
        usage = total / self.budget
        return ContextReport(
            total_tokens=total,
            budget=self.budget,
            usage_ratio=usage,
            should_compress=usage >= COMPRESS_THRESHOLD,
        )
