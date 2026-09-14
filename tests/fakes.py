from afg.context.messages import Message
from afg.llm.base import BaseLLM, LLMResponse


class FakeLLM(BaseLLM):
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
