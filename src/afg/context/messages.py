"""消息模型：Agent 上下文的最小原子，也是与 OpenAI 兼容 API 之间转换的唯一入口。

D1 规格（主文档「核心接口规格」）：Role / ToolCall / Message / TokenUsage。
D4 起 tools 模块将依赖这里的 ToolCall 解析结果。
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """LLM 返回的一次结构化工具调用指令。"""

    id: str  # LLM 返回的 call id
    name: str  # 工具名
    # 已 json.loads 的参数（注意：API 原始返回是 JSON 字符串，解析发生在 llm 层）
    arguments: dict[str, Any]


class Message(BaseModel):
    """一条对话消息，直接对应 OpenAI 协议 messages 数组里的一个元素。"""

    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # role=assistant 可有
    tool_call_id: str | None = None  # role=tool 时必填

    @model_validator(mode="after")
    def _check_role_tool(self) -> "Message":
        """role=tool 必须带 tool_call_id，否则 DeepSeek 侧会 400（新手第一大坑）。"""
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("role='tool' 的消息必须带 tool_call_id")
        return self


class TokenUsage(BaseModel):
    """单次响应的 token 用量统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens