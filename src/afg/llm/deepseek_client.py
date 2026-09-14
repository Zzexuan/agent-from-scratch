"""DeepSeek（或任意 OpenAI 兼容网关）客户端实现。

基座直接用 openai SDK，base_url 指向 DeepSeek 官方端点或本地网关，不手写 HTTP 层。
D1 只有 chat 的纯文本分支；`tools` 参数 D4 起启用。

新手阅读顺序：
1. 先读 __init__ 与 chat() 签名（它继承 base.py 的 BaseLLM）。
2. chat() 做的事一句话：把我们自己定义的 Message 列表翻译成 OpenAI 协议
   的 dict 列表发出去，再把 API 返回翻译回我们的 LLMResponse。
3. 记住两个"翻译"方向——【发出去：pydantic → dict → JSON】在 chat()
   前半段，"收回来：JSON → dict → pydantic 对象"在后半段，各看一遍即可。
"""

# openai 是 OpenAI 官方的 Python SDK。DeepSeek 的接口与 OpenAI 兼容，
# 所以我们不自己拼 HTTP，而是让 SDK 帮忙发请求，只需改 base_url 指向
# DeepSeek 的地址（见 config.py）。这也是整个项目的"LLM 接入方式"。
import json

from openai import OpenAI

from afg.config import LLMConfig  # 读取密钥/地址/模型名的配置类（见 config.py）
from afg.context.messages import Message, TokenUsage, ToolCall
from afg.llm.base import BaseLLM, LLMResponse


class DeepSeekClient(BaseLLM):
    """通过 openai SDK 与 OpenAI 兼容端点对话（默认 DeepSeek，可换网关）。

    名字里的 Client 指"API 的客户端"（调用方），不是"服务器"。
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        # 成员名前的下划线 _ 是 Python 约定：表示"私有成员，类内部使用，
        # 外部别直接碰"。只是约定不强制，但全项目遵守（可读性规则）。
        # OpenAI(...) 这一步就创建了连接句柄：以后每次 .chat() 都通过它发请求。
        self._client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    # 注意：这里必须和 base.py 里 BaseLLM.chat 的签名【完全一致】，
    # 因为 BaseLLM 用 @abstractmethod 规定了接口长相，子类照抄实现。
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,  # D1-D3 不用，先留接口位（见 base.py 同款注释）
        temperature: float = 0.7,
    ) -> LLMResponse:
        # 【发出去】把我们的 Message 对象翻译成 OpenAI 要的 dict 列表。
        # m.model_dump() = pydantic 的"对象 → 字典"方法（一行序列化）。
        # exclude_none=True 表示"值为 None 的字段直接丢弃，不发"——
        # 为什么要丢：比如纯文本消息的 tool_calls 是 None，DeepSeek 收到
        # 带 null 的字段可能报 400。我们这边"没有"就干脆不告诉它。
        payload: dict = {
            "model": self._config.model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            # ^ 这一行是【列表推导式】：对 messages 里每一个 m，算出
            #   m.model_dump(exclude_none=True)，收集成一个新列表。
            #   等价于：
            #     result = []
            #     for m in messages:
            #         result.append(m.model_dump(exclude_none=True))
            #   列表推导式是 Python 最常用的简写，读法："对 m 应用表达式"。
            "temperature": temperature,
        }
        # D4 起 tools 参数非空时，把工具描述也放进请求，模型才知道能调什么。
        if tools:
            payload["tools"] = tools

        # .create() 是 openai SDK 真正发 HTTP 请求的方法（同步阻塞等待返回）。
        # resp 是 SDK 封装好的响应对象，下面逐层取字段（用 . 一层层点进去）。
        resp = self._client.chat.completions.create(**payload)
        # 注意 create(**payload) 的 ** 语法：把 payload 这个字典的每个键
        # 展开成"关键字参数"传入。即 create(model=..., messages=..., temperature=...)。
        # choices[0].message：一次请求模型可能给多个候选答案(choices)，
        # 我们只取第一个；.message 就是那条 assistant 消息。
        msg = resp.choices[0].message

        # 【收回来】把 API 返回的工具调用翻译成我们的 ToolCall 对象。
        tool_calls: list[ToolCall] = []
        # msg.tool_calls or []：若 API 没返回工具调用，msg.tool_calls 是 None，
        # 直接 for 循环 None 会报错。or [] 的意思是"None 就当成空列表"，
        # 循环自然一次都不执行。这是处理"可选内容"的常用惯用法。
        for tc in msg.tool_calls or []:
            # 坑：API 返回的 arguments 是【JSON 字符串】，不是 Python 对象！
            # 例：'{"a": 1, "b": 2}' 这种文本。必须先 json.loads 解析成真正的
            # dict，我们的 ToolCall.arguments 字段才收得到字典。漏了这步，
            # 后面 tools 模块做参数校验时会拿到字符串而炸掉（D4 的战场）。
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))
            )

        used = resp.usage  # API 返回的 token 用量统计（prompt/completion）
        return LLMResponse(
            content=msg.content,  # 模型回复文本（无则 None，与 messages.py 呼应）
            tool_calls=tool_calls,
            # if used else 0 是【三元表达式】：`A if 条件 else B`
            # = "条件成立取 A，否则取 B"。有些网关不返回 usage，used 为
            # None，直接 used.prompt_tokens 会 AttributeError，所以兜底成 0。
            usage=TokenUsage(
                prompt_tokens=used.prompt_tokens if used else 0,
                completion_tokens=used.completion_tokens if used else 0,
            ),
        )