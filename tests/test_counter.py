"""D2 token 计数器单测：tiktoken 分支 / 回退估算 / 消息列表合计。零真实 API。

读法：每个 test_ 函数钉死 TokenCounter 的一个行为。先读两个"真家伙"
测试（对比 tiktoken 结果），再看"估算分支"和"合计"测试。
"""

import tiktoken  # 测试里直接用它当"标准答案"：被测代码算得和它一致 = 对

from afg.context.counter import TokenCounter
from afg.context.messages import Message


def test_count_english_uses_tiktoken() -> None:
    """英文文本：TokenCounter 的结果必须和 tiktoken 自己数的一模一样。"""
    text = "Hello, world! This is a token counting test."
    enc = tiktoken.get_encoding("cl100k_base")  # 拿到和 counter 同一个编码器
    assert TokenCounter().count(text) == len(enc.encode(text))  # 两边应相等


def test_count_chinese_mixed() -> None:
    """中英混合文本同样要对齐 tiktoken（中文计数口径容易错，单独测）。"""
    text = "你好，世界！这是中英文混合 123 的一段文本。"
    enc = tiktoken.get_encoding("cl100k_base")
    assert TokenCounter().count(text) == len(enc.encode(text))


def test_count_empty_text_is_zero() -> None:
    """空文本 → 0 个 token（counter.py 里 if not text 早退分支）。"""
    assert TokenCounter().count("") == 0


def test_count_fallback_estimation() -> None:
    """回退估算分支：prefer_tiktoken=False 强制走 len(text) * 0.6 估算。"""
    # 这个测试不联网、不依赖 tiktoken 包，验证"备胎"逻辑本身没写错。
    counter = TokenCounter(prefer_tiktoken=False)
    assert counter.count("你好世界") == int(len("你好世界") * 0.6)
    assert counter.count("") == 0  # 估算分支下空文本也必须是 0


def test_count_messages_sums_content() -> None:
    """count_messages：多条消息的 content 应逐条相加。"""
    counter = TokenCounter()
    messages = [
        Message(role="system", content="你是助手"),
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！有什么可以帮你？"),
    ]
    # 预期值 = 手工把每条 content 分别 count 再求和（m.content or "" 处理 None）
    expected = sum(counter.count(m.content or "") for m in messages)
    assert counter.count_messages(messages) == expected


def test_count_messages_includes_tool_calls() -> None:
    """工具消息也要计入：工具名 + 参数 JSON + call_id + tool 的 content 全算。

    这条对应 counter.py 里"为 D4 预留精确口径"的注释——发出去的每个
    字段都占 token，只数 content 会低估，所以测试钉死"全部都数"。
    """
    counter = TokenCounter()
    messages = [
        Message(
            role="assistant",
            content=None,
            tool_calls=[{"id": "call_1", "name": "calculator", "arguments": {"a": 1, "b": 2}}],
        ),
        Message(role="tool", content="3", tool_call_id="call_1"),
    ]
    expected = (
        counter.count("calculator")
        + counter.count('{"a": 1, "b": 2}')  # 与 counter.py 的 json.dumps 口径一致
        + counter.count("call_1")
        + counter.count("3")  # tool 消息的 content 同样计入
    )
    assert counter.count_messages(messages) == expected