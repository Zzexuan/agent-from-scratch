"""DeepSeek（或任意 OpenAI 兼容网关）客户端实现。

基座直接用 openai SDK，base_url 指向 DeepSeek 官方端点或本地网关，不手写 HTTP 层。
D1 只有 chat 的纯文本分支；`tools` 参数 D4 起启用。
"""

import json

from openai import OpenAI

from afg.config import LLMConfig
from afg.context.messages import Message, TokenUsage, ToolCall
from afg.llm.base import BaseLLM, LLMResponse


class DeepSeekClient(BaseLLM):
    """通过 openai SDK 与 OpenAI 兼容端点对话（默认 DeepSeek，可换网关）。"""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        payload: dict = {
            "model": self._config.model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        resp = self._client.chat.completions.create(**payload)
        msg = resp.choices[0].message

        tool_calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            # 坑：API 返回的 arguments 是 JSON 字符串，必须显式 json.loads。
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))
            )

        used = resp.usage
        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=used.prompt_tokens if used else 0,
                completion_tokens=used.completion_tokens if used else 0,
            ),
        )