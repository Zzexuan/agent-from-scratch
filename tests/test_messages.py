"""D1 消息模型单测：序列化往返 / role=tool 约束 / token 统计。零真实 API。"""

import pytest

from afg.context.messages import Message, TokenUsage


def test_message_serialization_roundtrip() -> None:
    msg = Message(role="user", content="你好")
    restored = Message.model_validate(msg.model_dump())
    assert restored == msg


def test_assistant_tool_calls_roundtrip() -> None:
    msg = Message(
        role="assistant",
        content=None,
        tool_calls=[{"id": "call_1", "name": "calculator", "arguments": {"a": 1, "b": 2}}],
    )
    restored = Message.model_validate(msg.model_dump())
    assert restored.tool_calls is not None
    assert restored.tool_calls[0].name == "calculator"
    assert restored.tool_calls[0].arguments == {"a": 1, "b": 2}


def test_role_tool_requires_tool_call_id() -> None:
    with pytest.raises(ValueError):
        Message(role="tool", content="42")


def test_role_tool_with_tool_call_id_ok() -> None:
    msg = Message(role="tool", content="42", tool_call_id="call_1")
    assert msg.tool_call_id == "call_1"


def test_token_usage_total() -> None:
    usage = TokenUsage(prompt_tokens=100, completion_tokens=40)
    assert usage.total == 140
    assert TokenUsage().total == 0