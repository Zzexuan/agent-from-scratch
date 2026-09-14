from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from afg.context.messages import TokenUsage, ToolCall


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages, tools=None, temperature=0.7):
        ...
