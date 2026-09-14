"""D1 消息模型单测：序列化往返 / role=tool 约束 / token 统计。零真实 API。

新手阅读顺序：
1. 先读 test_message_serialization_roundtrip（最基础：存进去能原样取出来）。
2. 再看 test_assistant_tool_calls_roundtrip（重点：dict 自动变成 ToolCall 对象）。
3. 其余是"校验规则"和"工具类"的测试，扫一眼即可。

pytest 约定：文件名 test_*.py、函数名 test_*，pytest 会自动发现并运行。
断言用 assert：条件为 False 时测试失败并报告。测试 = "把代码的行为
钉死成契约"——以后谁改坏了行为，跑一遍测试立刻红，当场抓出回归。
"""

import pytest  # 测试框架：pytest.raises 用来断言"应该抛异常"

from afg.context.messages import Message, TokenUsage


def test_message_serialization_roundtrip() -> None:
    """序列化往返：Message → dict → Message，内容应原样不变。"""
    msg = Message(role="user", content="你好")
    # model_dump() = pydantic 的"对象 → dict"（首次出现见 deepseek_client.py）。
    # model_validate(dict) = 反向：dict → 对象（按字段类型校验并重建）。
    # "往返"(roundtrip)：先转出去再转回来，等于"对象走了趟 API 传输"，应无损。
    restored = Message.model_validate(msg.model_dump())
    assert restored == msg  # pydantic 对象间 == 会逐字段比较内容


def test_assistant_tool_calls_roundtrip() -> None:
    """工具调用的往返：注意 tool_calls 传的是【dict 列表】也能自动变对象。

    这是 pydantic 最方便的能力之一：Message(tool_calls=[{...}]) 里传的是
    普通 dict，但 pydantic 看到字段类型是 list[ToolCall]，会自动把每个
    dict 转换成 ToolCall 对象——不需要我们手动构造。读代码时看到
    `restored.tool_calls[0].name` 能直接 .name，就是因为已经变对象了。
    """
    msg = Message(
        role="assistant",
        content=None,  # 带工具调用时没有文本回复，content 显式给 None（合法！）
        tool_calls=[{"id": "call_1", "name": "calculator", "arguments": {"a": 1, "b": 2}}],
    )
    restored = Message.model_validate(msg.model_dump())
    assert restored.tool_calls is not None  # 防 None：下面的 [0] 才不会炸
    assert restored.tool_calls[0].name == "calculator"  # 已是 ToolCall 对象，能 .name
    assert restored.tool_calls[0].arguments == {"a": 1, "b": 2}


def test_role_tool_requires_tool_call_id() -> None:
    """role=tool 却不带 tool_call_id → 应抛 ValueError（messages.py 的防呆校验）。"""
    # pytest.raises(ValueError) 上下文管理器：断言"里面的代码必须抛
    # ValueError"，不抛则测试失败。这正是测试"校验规则存在且生效"的写法。
    with pytest.raises(ValueError):
        Message(role="tool", content="42")  # 缺 tool_call_id → 构造时即报错


def test_role_tool_with_tool_call_id_ok() -> None:
    """带上 tool_call_id 后应正常构造，校验不再拦。"""
    msg = Message(role="tool", content="42", tool_call_id="call_1")
    assert msg.tool_call_id == "call_1"


def test_token_usage_total() -> None:
    """TokenUsage.total 是 @property：读起来像字段，值是实时相加的。"""
    usage = TokenUsage(prompt_tokens=100, completion_tokens=40)
    assert usage.total == 140  # 100 + 40
    assert TokenUsage().total == 0  # 不传参 → 两个字段默认 0 → total 也是 0