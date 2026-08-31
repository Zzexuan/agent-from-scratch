"""测试替身（mock 纪律）：脚本化返回序列的 FakeLLM，让所有单测零真实 API 调用。

D1 起立桩；D2 起 Compressor、D3 起的各种 loop 测试都复用这里的模式：
构造时传入按序返回的响应（str 或 LLMResponse），并记录每次调用的 messages。
"""

from afg.context.messages import Message
from afg.llm.base import BaseLLM, LLMResponse


class FakeLLM(BaseLLM):
    """按构造时传入的脚本依次返回固定响应，并记录每次调用参数。"""

    def __init__(self, responses: list[LLMResponse | str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("FakeLLM 响应序列已耗尽")
        item = self._responses.pop(0)
        if isinstance(item, str):
            item = LLMResponse(content=item)
        return item