"""LLM 客户端协议层：与具体厂商解耦的抽象。

为什么用 ABC 而不是 duck typing / Protocol（D1 八股记点）：
- 用 `@abstractmethod` 强制子类实现 chat()，接口契约在 import 时即成立，
  忘实现会立刻报错而非运行期 AttributeError——把契约错误提前到开发期。
- Protocol（structural）适合"鸭子类型自由组合"的场景（例如运算符协议），
  而 BaseLLM 是"实现方必须先显式声明继承关系"的 OOP 层次，ABC 更贴合。
- 额外能挂共享逻辑：参数校验、日志、重试（D6 的 with_retry 装饰器将加在这里）。
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from afg.context.messages import Message, TokenUsage, ToolCall


class LLMResponse(BaseModel):
    """一次 chat 的结构化返回：文本内容 + 工具调用意图 + token 用量。"""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class BaseLLM(ABC):
    """一切 LLM 供应商的统一入口（DeepSeek 官方 / 本地网关 / FakeLLM 都实现它）。"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,  # OpenAI 格式的 function schema 列表，D4 起启用
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送 messages（含历史）到模型，返回结构化响应，调用方自管消息列表。"""