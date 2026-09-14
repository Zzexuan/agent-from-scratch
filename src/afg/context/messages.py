from typing import Any, Literal

from pydantic import BaseModel, model_validator

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _check_role_tool(self) -> "Message":
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("role='tool' 的消息必须带 tool_call_id")
        return self


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens
