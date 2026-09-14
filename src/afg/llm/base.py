"""LLM 客户端协议层：与具体厂商解耦的抽象。

新手阅读顺序：
1. 先读 BaseLLM 类与 @abstractmethod 注释（本文件核心概念）。
2. 再看 LLMResponse 类（返回值长什么样）。
3. 最后回看模块顶部注释里的"为什么用 ABC"。
4. 配套看它的两个"儿子"：DeepSeekClient（真实现）与 tests/fakes.py 的
   FakeLLM（测试假实现）——它俩都继承 BaseLLM 并实现 chat()。

为什么用 ABC 而不是 duck typing / Protocol（D1 八股记点）：
- 用 `@abstractmethod` 强制子类实现 chat()，接口契约在 import 时即成立，
  忘实现会立刻报错而非运行期 AttributeError——把契约错误提前到开发期。
- Protocol（structural）适合"鸭子类型自由组合"的场景（例如运算符协议），
  而 BaseLLM 是"实现方必须先显式声明继承关系"的 OOP 层次，ABC 更贴合。
- 额外能挂共享逻辑：参数校验、日志、重试（D6 的 with_retry 装饰器将加在这里）。
"""

from abc import ABC, abstractmethod

# Field 是 pydantic 给字段"附加配置"的函数：默认值、校验规则、说明等。
from pydantic import BaseModel, Field

from afg.context.messages import Message, TokenUsage, ToolCall


class LLMResponse(BaseModel):
    """一次 chat 的结构化返回：文本内容 + 工具调用意图 + token 用量。

    DeepSeekClient.chat() 把 API 的原始响应整理成这个统一形状再返回，
    上层代码（chat.py / 未来的 AgentCore）只认 LLMResponse，不关心厂商。
    """

    content: str | None = None  # 模型回复的文本；没有文本则为 None（见 messages.py 同款注释）
    # Field(default_factory=list) 与直接写 `= []` 的区别——Python 经典大坑：
    # 默认值在【定义函数/类时】只创建一次。若写 tool_calls: list = []，
    # 所有没传 tool_calls 的 LLMResponse 实例会【共享同一个列表】，一个改了
    # 全跟着变。default_factory=list 则是"每次构造都新造一个空列表"，
    # 实例之间互不干扰。记口诀：可变类型（list/dict/set）的默认值一律用
    # default_factory，别直接写 = []。
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class BaseLLM(ABC):
    """一切 LLM 供应商的统一入口（DeepSeek 官方 / 本地网关 / FakeLLM 都实现它）。

    ABC 抽象类 = "只规定接口长相、不提供实现的半成品类"：
    - 类本身不能直接实例化（写 BaseLLM() 会报错），只能被继承；
    - 子类必须实现所有 @abstractmethod 方法，否则子类也无法实例化。
    效果：任何"想当 LLM 用"的类都必须实现 chat()，少一个就编译期报错，
    不会等到运行时才炸。整个项目只依赖这个抽象，换供应商零成本。
    """

    # @abstractmethod = 装饰器，声明"这是一个只有签名、没有实现的抽象方法"。
    # 子类（DeepSeekClient / FakeLLM）必须照这个签名写自己的 chat()。
    @abstractmethod
    def chat(
        self,
        messages: list[Message],  # 全部历史消息（含 system 指令），由调用方维护
        # list[dict] | None = None：tools 参数"要么是 dict 列表，要么不传"。
        # dict 是 OpenAI 格式的 function schema（描述工具有什么、参数怎么填），
        # D1-D3 用不到所以默认 None，D4 起启用。加 "| None" 允许调用方省略。
        tools: list[dict] | None = None,
        temperature: float = 0.7,  # 采样温度：越大越随机、越小越确定
    ) -> LLMResponse:
        """发送 messages（含历史）到模型，返回结构化响应，调用方自管消息列表。"""