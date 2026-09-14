from afg.llm.base import BaseLLM, LLMResponse


class FakeLLM(BaseLLM):
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.tool_schemas = []

    def chat(self, messages, tools=None, temperature=0.7):
        self.calls.append(list(messages))
        self.tool_schemas.append(tools)
        if not self._responses:
            raise AssertionError("FakeLLM 响应序列已耗尽")
        item = self._responses.pop(0)
        if type(item) == str:
            item = LLMResponse(content=item)
        return item
