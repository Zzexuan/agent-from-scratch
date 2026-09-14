import json

from openai import OpenAI

from afg.context.messages import TokenUsage, ToolCall
from afg.llm.base import BaseLLM, LLMResponse


def to_api_message(message):
    # 我们的 ToolCall 是扁平内部格式（id/name/arguments），但协议要求回传时
    # 必须带 type 且把 name/arguments 嵌进 function，arguments 还要还原成 JSON 字符串。
    # 漏掉 type 会被 API 拒绝：400 messages.N.tool_calls.0.type
    data = message.model_dump(exclude_none=True)
    if data.get("tool_calls"):
        api_calls = []
        for tc in data["tool_calls"]:
            api_calls.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
            )
        data["tool_calls"] = api_calls
    return data


class DeepSeekClient(BaseLLM):
    def __init__(self, config):
        self._config = config
        self._client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    def chat(self, messages, tools=None, temperature=0.7):
        clean_messages = []
        for m in messages:
            clean_messages.append(to_api_message(m))

        if tools:
            resp = self._client.chat.completions.create(
                model=self._config.model,
                messages=clean_messages,
                temperature=temperature,
                tools=tools,
            )
        else:
            resp = self._client.chat.completions.create(
                model=self._config.model,
                messages=clean_messages,
                temperature=temperature,
            )

        msg = resp.choices[0].message

        tool_call_list = msg.tool_calls
        if tool_call_list is None:
            tool_call_list = []

        tool_calls = []
        for tc in tool_call_list:
            arguments = json.loads(tc.function.arguments)
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))

        used = resp.usage
        if used:
            prompt_tokens = used.prompt_tokens
            completion_tokens = used.completion_tokens
        else:
            prompt_tokens = 0
            completion_tokens = 0

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )
