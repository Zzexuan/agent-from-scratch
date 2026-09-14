"""测试替身（mock 纪律）：脚本化返回序列的 FakeLLM，让所有单测零真实 API 调用。

新手阅读顺序：
1. 先读 FakeLLM 类的 __init__（它"假装自己是 LLM"）。
2. 再读 chat() 方法（每次被调用时吐一个预设答案）。
3. 回到 docstring 看"为什么测试要用假的"。

为什么测试要用 FakeLLM 而不是真调 DeepSeek：
① 快：真实 API 每次几百毫秒到几秒，几百个测试跑不完；
② 贵/有配额：任务书约定每天真实调用 ≤ 20 次，测试不该烧钱；
③ 确定性：真模型每次回答都随机，测试没法断言"它说了什么"；
   假模型按脚本返回固定内容，测试结果可重复、可预测；
④ 能测边界：让假模型"死循环返回同一动作""返回非法 JSON"等，逼真测试
   我们的熔断/报错逻辑——真模型很难稳定复现这些场景。
这就是"mock（模拟）"纪律：被测代码（如未来的 AgentCore）照常运行，
只是它依赖的"外部世界"（LLM）被换成了我们控制的替身。

FakeLLM 继承 BaseLLM（base.py 的抽象类）并实现 chat()——因为 BaseLLM
规定"所有 LLM 必须长这样"，FakeLLM 和 DeepSeekClient 是平级的两个实现，
一个真一个假。被测代码只认 BaseLLM，根本不知道自己是真是假。
"""

from afg.context.messages import Message
from afg.llm.base import BaseLLM, LLMResponse


class FakeLLM(BaseLLM):
    """按构造时传入的脚本依次返回固定响应，并记录每次调用参数。

    生活类比：拍戏时的"对戏演员"。导演（测试）告诉它"你第一句说 A、
    第二句说 B"，它就照背；同时它会把"对手（被测代码）每次递来的台词"
    原样记下来，方便导演事后检查。
    """

    def __init__(self, responses: list[LLMResponse | str]) -> None:
        # list[LLMResponse | str]：响应序列里每一项可以是 LLMResponse 对象
        # 或纯字符串。list(...) 拷贝一份传入的列表存成 self._responses，
        # 防止外部修改影响内部（浅拷贝足够，因为元素本身不改）。
        self._responses = list(responses)
        # self.calls 记录"每次 chat 被调用时收到的 messages 快照"，
        # 测试用它断言"被测代码确实把 user→assistant→tool 顺序发对了"。
        # 注意这里没有下划线：calls 是【测试要读的公共接口】，
        # 而 _responses 是内部实现细节，所以加 _ 表示"别从外部碰"。
        self.calls: list[list[Message]] = []

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,  # 签名必须与 BaseLLM 一致（见 base.py）
        temperature: float = 0.7,
    ) -> LLMResponse:
        # 每次被调用，先把收到的 messages 快照存进 calls（供事后断言）。
        # list(messages) 拷贝一份，避免外部之后修改 messages 影响记录。
        self.calls.append(list(messages))
        if not self._responses:  # 脚本已经用完了还来要 → 测试设计有 bug
            # AssertionError = "断言失败"：这里表示"响应序列耗尽"。
            # 让测试立刻失败并提示，而不是返回 None 然后报奇怪的错。
            raise AssertionError("FakeLLM 响应序列已耗尽")
        item = self._responses.pop(0)  # pop(0) = 取出并删除【第一个】元素
        # 这样每次调用依次吐 responses[0]、responses[1]……（脚本化出队）。
        if isinstance(item, str):
            # isinstance(对象, 类型)：判断 item 是不是 str 类型（运行时检查）。
            # 测试里常写 FakeLLM(["你好", "再见"]) 传纯字符串图省事，
            # 这里统一包装成 LLMResponse(content=...) 再返回，让调用方
            # 永远拿到 LLMResponse，不用区分两种类型。
            item = LLMResponse(content=item)
        return item