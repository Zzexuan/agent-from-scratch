"""D2 token 计数器单测：tiktoken 分支 / 回退估算 / 消息列表合计。零真实 API。"""

import tiktoken

from afg.context.counter import TokenCounter
from afg.context.messages import Message


def test_count_english_uses_tiktoken() -> None:
    text = "Hello, world! This is a token counting test."
    enc = tiktoken.get_encoding("cl100k_base")
    assert TokenCounter().count(text) == len(enc.encode(text))


def test_count_chinese_mixed() -> None:
    text = "你好，世界！这是中英文混合 123 的一段文本。"
    enc = tiktoken.get_encoding("cl100k_base")
    assert TokenCounter().count(text) == len(enc.encode(text))


def test_count_empty_text_is_zero() -> None:
    assert TokenCounter().count("") == 0


def test_count_fallback_estimation() -> None:
    # prefer_tiktoken=False 强制走估算分支：len(text) * 0.6 向下取整
    counter = TokenCounter(prefer_tiktoken=False)
    assert counter.count("你好世界") == int(len("你好世界") * 0.6)
    assert counter.count("") == 0


def test_count_messages_sums_content() -> None:
    counter = TokenCounter()
    messages = [
        Message(role="system", content="你是助手"),
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！有什么可以帮你？"),
    ]
    expected = sum(counter.count(m.content or "") for m in messages)
    assert counter.count_messages(messages) == expected


def test_count_messages_includes_tool_calls() -> None:
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
        + counter.count('{"a": 1, "b": 2}')
        + counter.count("call_1")
        + counter.count("3")  # tool 消息的 content 同样计入
    )
    assert counter.count_messages(messages) == expected